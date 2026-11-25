#!/usr/bin/env python3
"""Build the Marvel Minifigure Mystery catalogue from public LEGO catalog data.

Sources:
- Brickmaniacos Marvel minifigure directory (figure IDs, display names, first-year grouping)
- Rebrickable public CSV downloads (set appearances, release years, minifigure inventories)
- Rebrickable minifigure inventory parts (printed leg clue)

This script does not copy/rehost image files. It stores source image URLs.
"""
from __future__ import annotations
import csv, gzip, io, json, os, re, sys, time
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from html import unescape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures.json"
OVERRIDES = ROOT / "figure_overrides.json"
CATALOGUE_URL = "https://brickmaniacos.com/directorio/minifiguras/super-heroes-marvel"
DOWNLOAD_BASE = "https://cdn.rebrickable.com/media/downloads/"
DATA_DIR = Path(os.environ.get("LEGO_DATA_CACHE", ROOT / ".catalogue-cache"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

FILES = ["minifigs.csv.gz", "sets.csv.gz", "inventories.csv.gz", "inventory_minifigs.csv.gz", "parts.csv.gz", "inventory_parts.csv.gz"]
USER_AGENT = "MarvelMinifigureMystery/1.0 (fan catalogue; data attribution in README)"


def download(url: str, destination: Path, retries: int = 3) -> None:
    if destination.exists() and destination.stat().st_size > 100:
        return
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=90) as response, destination.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if destination.stat().st_size > 100:
                return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            if destination.exists():
                destination.unlink()
            if attempt == retries - 1:
                raise RuntimeError(f"Download failed for {url}: {exc}") from exc
            time.sleep(2 ** attempt)


def read_gz_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def fetch_catalogue() -> list[dict]:
    req = Request(CATALOGUE_URL, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as response:
        html = response.read().decode("utf-8", "replace")
    # Lightweight HTML parsing: figure links are standard anchors in the directory.
    # We track the year heading that precedes each figure list.
    from html.parser import HTMLParser
    class DirectoryParser(HTMLParser):
        def __init__(self):
            super().__init__(); self.items=[]; self.heading=False; self.heading_text=[]; self.current_year=None; self.anchor=None
        def handle_starttag(self, tag, attrs):
            attrs=dict(attrs)
            if tag in ("h2", "h3"):
                self.heading=True; self.heading_text=[]
            if tag == "a" and attrs.get("href", "").startswith("/minifig/fig-"):
                self.anchor={"href":attrs["href"],"text":[]}
        def handle_data(self, data):
            if self.heading: self.heading_text.append(data)
            if self.anchor is not None: self.anchor["text"].append(data)
        def handle_endtag(self, tag):
            if tag in ("h2", "h3") and self.heading:
                txt=" ".join(self.heading_text)
                year=re.search(r"\b(19\d{2}|20\d{2})\b",txt)
                self.current_year=int(year.group(1)) if year else None
                self.heading=False; self.heading_text=[]
            if tag == "a" and self.anchor is not None:
                href=self.anchor["href"]
                m=re.search(r"(fig-\d+)",href)
                name=" ".join(" ".join(self.anchor["text"]).split())
                if m and name:
                    name=re.sub(r"\s*\(fig-\d+\)\s*$","",name,flags=re.I).strip()
                    self.items.append({"id":m.group(1),"name":unescape(name),"directoryYear":self.current_year,"sourcePage":"https://brickmaniacos.com"+href})
                self.anchor=None
    parser=DirectoryParser(); parser.feed(html)
    # Deduplicate repeated links without losing source order.
    unique={}
    for item in parser.items: unique[item["id"]]=item
    result=list(unique.values())
    if len(result) < 600:
        raise RuntimeError(f"Catalogue parser only found {len(result)} figures; refusing to overwrite the data file.")
    return result


def load_overrides():
    if not OVERRIDES.exists(): return {}
    try: return json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except Exception: return {}


def main():
    for filename in FILES:
        download(DOWNLOAD_BASE + filename, DATA_DIR / filename)

    catalogue=fetch_catalogue()
    ids={x["id"] for x in catalogue}
    overrides=load_overrides()

    minifigs={}
    for row in read_gz_rows(DATA_DIR/"minifigs.csv.gz"):
        if row.get("fig_num") in ids:
            minifigs[row["fig_num"]]=row

    # Set metadata: set number base -> year. A figure's set appearances are
    # counted by distinct LEGO set numbers, not inventory versions.
    set_year={}
    for row in read_gz_rows(DATA_DIR/"sets.csv.gz"):
        base=row.get("set_num","").split("-")[0]
        try: year=int(row.get("year") or 0)
        except ValueError: year=0
        if base and year: set_year[base]=min(set_year.get(base,year),year)

    inventory_to_set={}
    figure_inventory_ids=defaultdict(list)
    for row in read_gz_rows(DATA_DIR/"inventories.csv.gz"):
        iid=row.get("id"); setnum=row.get("set_num","")
        if iid and setnum:
            inventory_to_set[iid]=setnum
            if setnum in ids: figure_inventory_ids[setnum].append(iid)

    appearances=defaultdict(set)
    for row in read_gz_rows(DATA_DIR/"inventory_minifigs.csv.gz"):
        fig=row.get("fig_num"); iid=row.get("inventory_id")
        if fig in ids and iid in inventory_to_set:
            setnum=inventory_to_set[iid].split("-")[0]
            if setnum in set_year:
                appearances[fig].add(setnum)

    # Build a part-number set for each catalogue figure. inventory_parts is
    # streamed in chunks to avoid loading the whole global file into memory.
    figure_inv_to_fig={iid:fig for fig,iids in figure_inventory_ids.items() for iid in iids}
    figure_parts=defaultdict(set)
    invparts_path=DATA_DIR/"inventory_parts.csv.gz"
    with gzip.open(invparts_path,"rt",encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        for row in reader:
            fig=figure_inv_to_fig.get(row.get("inventory_id"))
            if fig:
                figure_parts[fig].add(row.get("part_num","").lower())

    override_by_name={}
    for name, values in overrides.items():
        override_by_name[name_key(name)]=values

    output=[]
    for item in catalogue:
        fid=item["id"]
        rb=minifigs.get(fid,{})
        sets=sorted(appearances.get(fid,set()),key=lambda x:(int(re.match(r"\d+",x).group(0)) if re.match(r"\d+",x) else 0,x))
        year=item["directoryYear"]
        if not year:
            years=[set_year.get(s) for s in sets if set_year.get(s)]
            year=min(years) if years else None
        ov=override_by_name.get(name_key(item["name"])+"|"+str(year),{}) or override_by_name.get(name_key(item["name"]),{})
        parts=figure_parts.get(fid,set())
        leg_parts=[p for p in parts if p.startswith("970c00")]
        if any(re.match(r"970c00(?:pb|pr)",p) for p in leg_parts): legs="Yes"
        elif "970c00" in leg_parts: legs="No"
        else: legs=ov.get("legs")
        # Strong, inventory-based obvious unique sculpt examples only; leave
        # ambiguous molds blank rather than claiming a unique mold from print.
        unique_mold=ov.get("mold")
        if unique_mold is None and any(p.startswith(("90398","90399","90390")) for p in parts):
            unique_mold="Yes"
        figure={
            "id":fid,"name":item["name"],"year":year,
            "universe":ov.get("universe"),"role":ov.get("role"),
            "legs":legs,"sets":len(sets) if sets else None,"mold":unique_mold,
            "image":f"https://cdn.rebrickable.com/media/sets/{fid}.jpg",
            "setNumbers":sets,
            "sourcePage":item["sourcePage"],
            "dataSource":"Brickmaniacos directory + Rebrickable public catalogue/inventories",
            "attributeNotes":{
                "year":"Brickmaniacos first-year directory group; Rebrickable first set year used when directory year is absent",
                "sets":"Distinct set numbers from Rebrickable inventory minifigure links",
                "legs":"Rebrickable minifigure inventory leg part number; blank if no leg component could be identified",
                "universe":"Existing spreadsheet value; not independently sourced by this automated catalogue update" if ov.get("universe") else "Needs variant-specific verification",
                "role":"Existing spreadsheet value; needs review if uncertain" if ov.get("role") else "Needs character-role review",
                "mold":"Existing spreadsheet value or obvious large-figure mold; otherwise left blank pending visual/part review"
            }
        }
        output.append(figure)
    output.sort(key=lambda f:(f["year"] or 0,f["name"].casefold(),f["id"]),reverse=True)
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Wrote {len(output)} catalogue figures to {OUT}")
    if len(output)<600: raise RuntimeError("Output count unexpectedly low; refusing to treat this as a full catalogue.")


def name_key(value):
    import unicodedata
    value=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    value=re.sub(r"[^a-z0-9]+"," ",value)
    return " ".join(value.split())

if __name__ == "__main__":
    main()
