# Marvel Minifigure Mystery — catalogue updater

This package adds automatic catalogue enrichment to the static GitHub Pages game.

## What the updater fills from online catalogue data

- Full Marvel minifigure directory and exact figure IDs/names from Brickmaniacos.
- First release year from the directory, with Rebrickable set-year fallback.
- Number of distinct sets and the set-number list from Rebrickable inventory links.
- Image URL for each exact minifigure variant (Rebrickable CDN; images are not copied into this repo).
- Printed-leg clue where the Rebrickable minifigure inventory contains a printed leg part.

It preserves existing spreadsheet Universe/Role/Mold values by exact normalized display-name match. It deliberately leaves uncertain Universe, Role, and Unique Mold fields blank rather than presenting a guess as verified. Those attributes need variant-specific source review; they are not consistently supplied as fields in the public inventory CSVs.

## Files

- `index.html` — Weddle-style game board with minifigure thumbnails.
- `figures.json` — initial seed generated from the current spreadsheet; the workflow replaces it with the full online catalogue.
- `figure_overrides.json` — existing reviewed/AI-assisted attribute values keyed by exact figure name.
- `scripts/update_catalogue.py` — online catalogue builder.
- `.github/workflows/update-catalogue.yml` — manual and weekly GitHub Actions update.

## Install into your GitHub repository

Extract this ZIP. In the repository's **Add file → Upload files** screen, upload/replace `index.html`, `figures.json`, and `figure_overrides.json`, and upload `scripts/update_catalogue.py` to a `scripts` folder. Upload `.github/workflows/update-catalogue.yml` into the `.github/workflows` folder (create the folders if GitHub's web uploader does not preserve them).

Then open **Actions → Update Marvel minifigure catalogue → Run workflow**. The workflow downloads the public CSV snapshots, creates the complete `figures.json`, and commits it. GitHub Pages should publish the new data automatically.

If Actions is disabled, enable it in the repository's Actions tab. The workflow requires the repository's default `GITHUB_TOKEN` to have write permission to contents; this is configured by the workflow's `permissions` block.

## Data sources and attribution

- Brickmaniacos Marvel minifigure directory: https://brickmaniacos.com/directorio/minifiguras/super-heroes-marvel
- Rebrickable public catalogue downloads: https://rebrickable.com/downloads/
- 
- Rebrickable image CDN: https://cdn.rebrickable.com/media/sets/

LEGO and Marvel are trademarks of their respective owners. This is an unofficial fan project and is not affiliated with or endorsed by LEGO, Marvel, Brickmaniacos, or Rebrickable. Images are referenced from their source and are not redistributed in this package. Please review each source's terms and attribution requirements before public launch.
