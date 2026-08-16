# NUPPL Flora Catalog — Raw Data Handover

A working, browsable catalog of 92 species (trees, shrubs, herbs, grasses) built from the raw field folders in this repo, for handover to the design team ahead of the print/magazine layout.

**Live site:** published via GitHub Pages from the `docs/` folder (see repo "About" section / Pages settings for the URL once enabled).

## Structure

- `TREES/`, `SHRUBS/`, `HERBS/`, `GRASS/` — raw source data. One folder per species, each containing:
  - one or more `.txt` files with common name, scientific name, family, habitat and economic/ecological importance notes
  - one or more field photos (`.jpg`/`.jpeg`)
- `scripts/build_site.py` — generates the static website from the raw folders into `docs/`. Re-run it any time a `.txt` file is edited or a photo is added/replaced:
  ```
  python3 scripts/build_site.py
  ```
- `docs/` — the generated static site (index + one profile page per plant). **Do not hand-edit files in here** — they're overwritten every time the build script runs.

## Known follow-up items for the design team

1. **Photos need a professional upgrade.** Every profile currently shows the original mobile field photo(s) only, clearly there as a placeholder. Several of these photos have a **visible burned-in GPS/timestamp watermark** (date, time, lat/long) in the bottom-left corner — these must **not** be used in the final magazine and should be replaced with high-resolution, non-geotagged photography (full plant, leaves, flowers, fruit where applicable).
2. **Multiple photos per species** (full plant / leaf close-up / flower / fruit) are not yet available for most entries — only 1–2 field photos exist per plant today.
3. Some `.txt` source notes only had a single free-text description (no distinct Habitat vs. Importance headings); those were parsed heuristically and may need a manual proofread pass.

## Editing plant data

Edit the relevant `.txt` file(s) inside the species folder (keep the `Common name:` / `Scientific name:` / `Family:` / `Habitat:` / `Economic importance:` style headings for best results), replace/add photos in the same folder, then re-run `python3 scripts/build_site.py`.
