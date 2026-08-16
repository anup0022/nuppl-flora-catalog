#!/usr/bin/env python3
"""Generates the static NUPPL-style flora catalog site into ./docs from the raw
plant folders (TREES/HERBS/SHRUBS/GRASS). Re-run after editing any .txt file
or adding photos; it fully regenerates docs/ each time."""
import os
import re
import shutil
import json
import subprocess
import time
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

CATEGORIES = [
    ("TREES", "Trees", "tree"),
    ("HERBS", "Herbs", "herb"),
    ("SHRUBS", "Shrubs", "shrub"),
    ("GRASS", "Grasses", "grass"),
]

IMG_EXTS = (".jpg", ".jpeg", ".png")
COMMONS_MANIFEST = os.path.join(ROOT, "data", "commons_images.json")


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def clean_name(folder_name):
    # collapse double spaces / stray parens spacing used in the raw folder names
    name = re.sub(r"\s+", " ", folder_name).strip()
    return name


# 1 hero photo + 4 Visual record photos per plant
COMMONS_TARGET = 5
NON_SPECIES_TOKENS = {"spp", "sp", "cv", "var", "subsp"}


def scientific_search_terms(scientific_name):
    """Return (primary two-word term, genus-only fallback term)."""
    words = [w for w in re.findall(r"[A-Za-z]+", scientific_name or "") if w.lower() not in NON_SPECIES_TOKENS]
    primary = " ".join(words[:2]) if len(words) >= 2 else ""
    genus = words[0] if words else ""
    return primary, genus


def _commons_search(term, tokens, limit, exclude_titles):
    if not term or limit <= 0:
        return []
    query = urllib.parse.urlencode({
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": term,
        "gsrnamespace": "6",
        "gsrlimit": "20",
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": "1400",
    })
    api_url = f"https://commons.wikimedia.org/w/api.php?{query}"
    payload = None
    for attempt in range(3):
        time.sleep(1.1)
        try:
            result = subprocess.run(
                ["curl", "-ksL", "--max-time", "20", "-A", "NUPPL-Flora-Catalog/1.0", api_url],
                check=True,
                capture_output=True,
                text=True,
            )
            if "too many requests" in result.stdout.lower():
                time.sleep(8)
                continue
            payload = json.loads(result.stdout)
            break
        except (subprocess.SubprocessError, json.JSONDecodeError):
            time.sleep(3)
    if payload is None:
        return []

    matches = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        title = page.get("title", "")
        title_lower = title.lower()
        clean_title = title.removeprefix("File:")
        if clean_title in exclude_titles:
            continue
        if not all(token in title_lower for token in tokens):
            continue
        if info.get("mime") not in ("image/jpeg", "image/png") or not info.get("thumburl"):
            continue
        metadata = info.get("extmetadata", {})
        matches.append({
            "title": clean_title,
            "url": info["thumburl"],
            "source": "Wikimedia Commons",
            "license": metadata.get("LicenseShortName", {}).get("value", "Commons license"),
        })
        if len(matches) == limit:
            break
    return matches


def fetch_commons_images(plant):
    primary_term, genus_term = scientific_search_terms(plant["scientific_name"])
    if not primary_term and not genus_term:
        return []

    os.makedirs(os.path.dirname(COMMONS_MANIFEST), exist_ok=True)
    manifest = {}
    if os.path.exists(COMMONS_MANIFEST):
        with open(COMMONS_MANIFEST, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)

    matches = list(manifest.get(plant["slug"], []))
    if len(matches) >= COMMONS_TARGET:
        return matches

    seen_titles = {m["title"] for m in matches}
    if primary_term:
        for m in _commons_search(primary_term, primary_term.lower().split(), COMMONS_TARGET - len(matches), seen_titles):
            matches.append(m)
            seen_titles.add(m["title"])
    if len(matches) < COMMONS_TARGET and genus_term:
        for m in _commons_search(genus_term, [genus_term.lower()], COMMONS_TARGET - len(matches), seen_titles):
            matches.append(m)
            seen_titles.add(m["title"])

    manifest[plant["slug"]] = matches
    with open(COMMONS_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return matches


HEADING_RULES = [
    ("habitat", "habitat"),
    ("growth form", "habitat"),
    ("features", "habitat"),
    ("economic & medicinal importance", "economic"),
    ("economic and medicinal importance", "economic"),
    ("economic importance", "economic"),
    ("ecological importance", "economic"),
    ("ecological", "economic"),
    ("importance", "economic"),
    ("medicinal importance", "medicinal"),
    ("medicinal", "medicinal"),
    ("other uses", "other"),
    ("other", "other"),
    ("uses & importance", "other"),
]

SKIP_HEADING_STARTS = (
    "probable identification",
    "name & scientific",
    "name and scientific",
)


def parse_txt(text):
    data = {"common_name": None, "scientific_name": None, "family": None, "ptype": None}
    sections = {"habitat": [], "economic": [], "medicinal": [], "other": []}
    current = "other"

    labels = (
        "Common name", "Scientific name", "Plant Type", "Family", "Synonym",
        "Habitat", "Growth form", "Features", "Economic importance",
        "Ecological importance", "Ecological", "Medicinal importance", "Medicinal",
        "Other uses",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    text = re.sub(
        rf"(?<!^)(?<!\n)(?=({label_pattern})\s*:)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        detect = re.sub(r"^[^A-Za-z]+", "", raw)
        lower = detect.lower()

        if lower.startswith("common name"):
            if ":" in raw:
                data["common_name"] = raw.split(":", 1)[1].strip()
            continue
        if lower.startswith("scientific name"):
            if ":" in raw:
                data["scientific_name"] = raw.split(":", 1)[1].strip()
            continue
        if lower.startswith("family"):
            if ":" in raw:
                data["family"] = raw.split(":", 1)[1].strip()
            continue
        if lower.startswith("plant type") or lower.startswith("type"):
            if ":" in raw:
                data["ptype"] = raw.split(":", 1)[1].strip()
            continue
        if lower.startswith(SKIP_HEADING_STARTS):
            continue

        matched_heading = False
        for prefix, section in HEADING_RULES:
            if lower.startswith(prefix):
                current = section
                if ":" in raw:
                    after = raw.split(":", 1)[1].strip()
                    if after:
                        sections[current].append(after)
                matched_heading = True
                break
        if matched_heading:
            continue

        content_line = re.sub(r"^[\-\*\u2022]\s*", "", raw)
        sections[current].append(content_line)

    return data, sections


def build():
    if os.path.exists(DOCS):
        shutil.rmtree(DOCS)
    os.makedirs(os.path.join(DOCS, "assets", "img"))
    os.makedirs(os.path.join(DOCS, "plants"))

    all_plants = []  # for index + prev/next navigation
    by_category = {}

    for folder, label, badge in CATEGORIES:
        cat_path = os.path.join(ROOT, folder)
        if not os.path.isdir(cat_path):
            continue
        plant_dirs = sorted(
            [d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d))],
            key=lambda s: s.lower(),
        )
        plants = []
        for plant_dir in plant_dirs:
            plant_path = os.path.join(cat_path, plant_dir)
            files = os.listdir(plant_path)
            txt_files = sorted(f for f in files if f.lower().endswith(".txt"))
            img_files = sorted(f for f in files if f.lower().endswith(IMG_EXTS))

            combined_text = ""
            for tf in txt_files:
                with open(os.path.join(plant_path, tf), "r", encoding="utf-8", errors="ignore") as fh:
                    combined_text += fh.read() + "\n\n"

            data, sections = parse_txt(combined_text)
            display_name = clean_name(plant_dir)
            slug = slugify(f"{badge}-{display_name}")

            # copy photos
            img_dir = os.path.join(DOCS, "assets", "img", slug)
            copied_imgs = []
            if img_files:
                os.makedirs(img_dir, exist_ok=True)
                for i, imf in enumerate(img_files, start=1):
                    dest_name = f"photo-{i}.jpg"
                    shutil.copy2(os.path.join(plant_path, imf), os.path.join(img_dir, dest_name))
                    copied_imgs.append(f"assets/img/{slug}/{dest_name}")

            commons_images = fetch_commons_images({
                "slug": slug,
                "scientific_name": data["scientific_name"],
            })

            plant = {
                "slug": slug,
                "display_name": display_name,
                "category_folder": folder,
                "category_label": label,
                "badge": badge,
                "common_name": data["common_name"] or display_name,
                "scientific_name": data["scientific_name"],
                "family": data["family"],
                "ptype": data["ptype"],
                "habitat": sections["habitat"],
                "economic": sections["economic"],
                "medicinal": sections["medicinal"],
                "other": sections["other"],
                "images": copied_imgs,
                "commons_images": commons_images,
            }
            plants.append(plant)
            all_plants.append(plant)
        by_category[folder] = {"label": label, "badge": badge, "plants": plants}

    render_index(by_category)
    for i, plant in enumerate(all_plants):
        prev_p = all_plants[i - 1] if i > 0 else None
        next_p = all_plants[i + 1] if i < len(all_plants) - 1 else None
        render_plant_page(plant, prev_p, next_p)

    write_css()
    write_readme_data(by_category)
    print(f"Built {len(all_plants)} plant pages across {len(by_category)} categories into {DOCS}")


def esc(text):
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_list(items):
    if not items:
        return ""
    lis = "\n".join(f"        <li>{esc(item)}</li>" for item in items)
    return f"      <ul>\n{lis}\n      </ul>"


def base_head(title, depth=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,500&family=Work+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{depth}assets/style.css">
</head>
"""


def render_index(by_category):
    total = sum(len(c["plants"]) for c in by_category.values())
    featured = []
    for category in by_category.values():
        for plant in category["plants"]:
            if plant["images"]:
                featured.append(plant)
    featured = featured[:6]
    hero_images = "\n".join(
        f'<figure class="hero-photo hero-photo-{i + 1}"><img src="{p["images"][0]}" alt="{esc(p["display_name"])}" loading="eager"><figcaption>{esc(p["display_name"])}</figcaption></figure>'
        for i, p in enumerate(featured)
    )
    sections_html = []
    for folder, label, badge in CATEGORIES:
        cat = by_category.get(folder)
        if not cat or not cat["plants"]:
            continue
        items = "\n".join(
            f'          <li><a class="index-link" href="plants/{p["slug"]}.html">{esc(p["display_name"])}'
            + (f'<span class="sci">{esc(p["scientific_name"])}</span>' if p["scientific_name"] else "")
            + "</a></li>"
            for p in cat["plants"]
        )
        sections_html.append(f"""
      <section class="cat-block cat-{badge}" id="{folder.lower()}">
        <h2><span class="cat-count">{len(cat['plants']):02d}</span>{esc(label)}</h2>
        <ul class="index-grid" data-filterable>
{items}
        </ul>
      </section>""")

    html = base_head("NUPPL Flora Catalog \u2014 Full Index") + f"""<body>
<header class="site-header">
  <div class="hero-copy">
    <p class="eyebrow">NUPPL Flora Catalog</p>
    <h1>The Green Register</h1>
    <p class="tagline">A working catalog of {total} campus &amp; local species &mdash; trees, shrubs, herbs and grasses.</p>
    <input id="search" type="search" placeholder="Search the register by name..." autocomplete="off">
  </div>
  <div class="hero-collage" aria-label="Selected plant photographs">
{hero_images}
  </div>
</header>
<main>
{''.join(sections_html)}
</main>
<footer class="site-footer">
  <p>Raw data compiled for internal handover &middot; photos are field references pending professional replacement &middot; generated automatically from source notes.</p>
</footer>
<script>
const input = document.getElementById('search');
input.addEventListener('input', () => {{
  const q = input.value.trim().toLowerCase();
  document.querySelectorAll('[data-filterable] li').forEach(li => {{
    li.style.display = li.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
  document.querySelectorAll('.cat-block').forEach(block => {{
    const visible = [...block.querySelectorAll('li')].some(li => li.style.display !== 'none');
    block.style.display = visible ? '' : 'none';
  }});
}});
</script>
</body>
</html>
"""
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)


def render_plant_page(plant, prev_p, next_p):
  hero_external = plant.get("commons_images", [{}])[0].get("url", "") if plant.get("commons_images") else ""
  hero_src = hero_external or (plant["images"][0] if plant["images"] else "")
  visual_commons = [source for source in plant.get("commons_images", []) if source.get("url") != hero_external]
  visual_local = plant["images"][1:] if plant["images"] else []
  visual_count = len(visual_commons) + len(visual_local)
  gallery = ""
  if visual_count:
    figs = []
    for i, source in enumerate(visual_commons):
      figs.append(
        f'      <figure class="gallery-item gallery-external gallery-item-{i + 1}"><img src="{esc(source["url"])}" alt="{esc(plant["display_name"])} reference image from Wikimedia Commons" loading="lazy"><figcaption>{esc(source["source"])} · {esc(source["license"])}</figcaption></figure>'
      )
    for i, src in enumerate(visual_local, start=len(figs) + 1):
      figs.append(
        f'      <figure class="gallery-item gallery-item-{i}"><img src="../{src}" alt="{esc(plant["display_name"])} field photo {i}" loading="lazy"><figcaption>Field reference {i:02d}</figcaption></figure>'
      )
    gallery_body = "\n".join(figs)
    gallery = (
      f'<section class="gallery gallery-footer"><div class="gallery-heading"><span>Visual record</span>'
      f'<strong>{visual_count:02d} additional photographs</strong></div>'
      f'<div class="gallery-grid">\n{gallery_body}\n    </div></section>'
    )
  else:
    gallery = '<section class="gallery gallery-footer gallery-empty"><p>No additional reference photographs on file yet.</p></section>'

  facts_rows = []
  if plant["scientific_name"]:
      facts_rows.append(f'<tr><th>Scientific name</th><td class="sci">{esc(plant["scientific_name"])}</td></tr>')
  if plant["family"]:
      facts_rows.append(f'<tr><th>Family</th><td>{esc(plant["family"])}</td></tr>')
  if plant["ptype"]:
      facts_rows.append(f'<tr><th>Type</th><td>{esc(plant["ptype"])}</td></tr>')
  facts_rows.append(f'<tr><th>Category</th><td>{esc(plant["category_label"])}</td></tr>')
  facts_table = "<table class=\"facts\">\n" + "\n".join(facts_rows) + "\n</table>"

  habitat_html = render_list(plant["habitat"]) or "<p class=\"muted\">Habitat notes pending.</p>"
  economic_html = render_list(plant["economic"]) or "<p class=\"muted\">Economic notes pending.</p>"
  medicinal_html = render_list(plant["medicinal"]) or "<p class=\"muted\">Medicinal notes pending.</p>"
  other_html = f'<section class="block"><h3>Field Notes</h3>{render_list(plant["other"])}</section>' if plant["other"] else ""
  hero_image = (
    f'<img src="{esc(hero_src)}" alt="{esc(plant["display_name"])} specimen photograph" loading="eager">'
    if hero_external else
    f'<img src="../{hero_src}" alt="{esc(plant["display_name"])} specimen photograph" loading="eager">'
  ) if hero_src else ""
  inline_src = plant["images"][1] if len(plant["images"]) > 1 else ""
  inline_image = (
    f'<img src="../{inline_src}" alt="{esc(plant["display_name"])} field detail" loading="lazy">'
    if inline_src else
    f'<img src="{esc(plant["commons_images"][0]["url"])}" alt="{esc(plant["display_name"])} reference detail" loading="lazy">'
    if plant.get("commons_images") else ""
  )
  inline_photo = (
    f'<figure class="inline-photo">{inline_image}<figcaption>Field detail</figcaption></figure>'
    if inline_image else ""
  )

  nav_links = []
  if prev_p:
      nav_links.append(f'<a class="nav-link prev" href="{prev_p["slug"]}.html">&larr; {esc(prev_p["display_name"])}</a>')
  else:
      nav_links.append('<span></span>')
  if next_p:
      nav_links.append(f'<a class="nav-link next" href="{next_p["slug"]}.html">{esc(next_p["display_name"])} &rarr;</a>')
  else:
      nav_links.append('<span></span>')

  html = base_head(f'{plant["display_name"]} \u2014 NUPPL Flora Catalog', depth="../") + f"""<body class="plant-page cat-{plant['badge']}">
<header class="plant-header">
  <a class="back-link" href="../index.html#{plant['category_folder'].lower()}">&larr; Full Index</a>
  <div class="plant-hero">
    <div class="plant-hero-copy">
      <p class="eyebrow">{esc(plant['category_label'])} Specimen</p>
      <h1>{esc(plant['display_name'])}</h1>
      {f'<p class="common-alt">Also known as: {esc(plant["common_name"])}</p>' if plant["common_name"] and plant["common_name"] != plant["display_name"] else ''}
    </div>
    {f'<div class="plant-hero-image">{hero_image}</div>' if hero_image else ''}
  </div>
</header>
<main class="plant-main">
  <div class="content-grid">
    <div class="col-facts">
      {facts_table}
    </div>
    <div class="col-text">
      <section class="block">
        <h3>Habitat &amp; Growing Conditions</h3>
        {habitat_html}
      </section>
      {inline_photo}
      <section class="block">
        <h3>Economic Importance</h3>
        {economic_html}
      </section>
      <section class="block">
        <h3>Medicinal Importance</h3>
        {medicinal_html}
      </section>
      {other_html}
    </div>
  </div>
  {gallery}
</main>
<nav class="plant-nav">
  {nav_links[0]}
  <a class="nav-link index" href="../index.html">Index</a>
  {nav_links[1]}
</nav>
</body>
</html>
"""
  with open(os.path.join(DOCS, "plants", f"{plant['slug']}.html"), "w", encoding="utf-8") as fh:
    fh.write(html)


def write_readme_data(by_category):
    summary = {folder: len(cat["plants"]) for folder, cat in by_category.items()}
    with open(os.path.join(DOCS, "counts.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)


def write_css():
    css = """
:root {
  --paper: #f4efe4;
  --paper-deep: #ece4d3;
  --ink: #23281f;
  --ink-soft: #58604f;
  --green: #24422c;
  --green-deep: #17301d;
  --link-blue: #1450c9;
  --link-blue-visited: #3a3ab0;
  --tree: #1f5c3a;
  --shrub: #7a6a1e;
  --herb: #b5541f;
  --grass: #4d7a1f;
  --rule: rgba(35, 40, 31, 0.18);
  font-size: 17px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Work Sans", -apple-system, sans-serif;
  line-height: 1.55;
  background-image:
    radial-gradient(circle at 15% 8%, rgba(36, 66, 44, 0.06), transparent 40%),
    radial-gradient(circle at 85% 92%, rgba(181, 84, 31, 0.06), transparent 45%);
}

h1, h2, h3 {
  font-family: "Fraunces", serif;
  color: var(--green-deep);
  line-height: 1.15;
  margin: 0 0 0.4em;
}

a { color: inherit; text-decoration: none; }

.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink-soft);
  margin: 0 0 0.6em;
}

/* ---------- Index page ---------- */
.site-header {
  max-width: 900px;
  margin: 0 auto;
  padding: 4.5rem 1.5rem 2.5rem;
  text-align: center;
}
.site-header h1 {
  font-size: clamp(2.4rem, 6vw, 4rem);
  font-style: italic;
  font-weight: 600;
}
.tagline {
  color: var(--ink-soft);
  max-width: 560px;
  margin: 0.8rem auto 2rem;
}
#search {
  width: 100%;
  max-width: 420px;
  padding: 0.7rem 1rem;
  border: 1.5px solid var(--rule);
  border-radius: 999px;
  background: rgba(255,255,255,0.6);
  font-family: "Work Sans", sans-serif;
  font-size: 0.95rem;
  color: var(--ink);
}
#search:focus { outline: 2px solid var(--green); }

main { max-width: 1080px; margin: 0 auto; padding: 0 1.5rem 4rem; }

.cat-block {
  border-top: 1px solid var(--rule);
  padding: 2.4rem 0;
}
.cat-block h2 {
  font-size: 1.9rem;
  display: flex;
  align-items: baseline;
  gap: 0.7rem;
  font-style: italic;
}
.cat-count {
  font-family: "Work Sans", sans-serif;
  font-style: normal;
  font-weight: 600;
  font-size: 0.85rem;
  color: #fff;
  background: var(--ink-soft);
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
}
.cat-tree .cat-count { background: var(--tree); }
.cat-shrub .cat-count { background: var(--shrub); }
.cat-herb .cat-count { background: var(--herb); }
.cat-grass .cat-count { background: var(--grass); }

.index-grid {
  list-style: none;
  margin: 1.4rem 0 0;
  padding: 0;
  columns: 3 220px;
  column-gap: 2rem;
}
.index-grid li { break-inside: avoid; margin-bottom: 0.55rem; }

.index-link {
  color: var(--link-blue);
  font-weight: 500;
  border-bottom: 1px solid transparent;
  display: block;
}
.index-link:hover { border-bottom-color: var(--link-blue); }
.index-link .sci {
  display: block;
  font-style: italic;
  font-size: 0.78rem;
  color: var(--ink-soft);
  font-weight: 400;
}

.site-footer {
  text-align: center;
  color: var(--ink-soft);
  font-size: 0.82rem;
  padding: 2rem 1.5rem 3rem;
  max-width: 640px;
  margin: 0 auto;
}

/* ---------- Plant page ---------- */
.plant-header {
  max-width: 900px;
  margin: 0 auto;
  padding: 2.6rem 1.5rem 1.2rem;
}
.back-link {
  color: var(--ink-soft);
  font-size: 0.85rem;
  display: inline-block;
  margin-bottom: 1.4rem;
}
.back-link:hover { color: var(--green); }
.plant-header h1 {
  font-size: clamp(2rem, 5vw, 3rem);
  font-style: italic;
}
.common-alt { color: var(--ink-soft); margin-top: -0.2rem; }

.plant-page.cat-tree .eyebrow { color: var(--tree); }
.plant-page.cat-shrub .eyebrow { color: var(--shrub); }
.plant-page.cat-herb .eyebrow { color: var(--herb); }
.plant-page.cat-grass .eyebrow { color: var(--grass); }

.plant-main { max-width: 900px; margin: 0 auto; padding: 0 1.5rem 2rem; }

.gallery {
  display: flex;
  gap: 0.9rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
  margin-bottom: 2rem;
}
.gallery figure { margin: 0; flex: 0 0 auto; }
.gallery img {
  height: 320px;
  width: auto;
  max-width: 88vw;
  object-fit: cover;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(23, 48, 29, 0.18);
  background: var(--paper-deep);
}
.gallery-empty {
  background: var(--paper-deep);
  border-radius: 10px;
  padding: 2.5rem;
  text-align: center;
  color: var(--ink-soft);
}

.content-grid {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 2.5rem;
}
@media (max-width: 640px) {
  .content-grid { grid-template-columns: 1fr; }
  .index-grid { columns: 1 220px; }
}

.facts {
  width: 100%;
  border-collapse: collapse;
  background: rgba(255,255,255,0.5);
  border-radius: 10px;
  overflow: hidden;
  font-size: 0.9rem;
}
.facts th, .facts td {
  text-align: left;
  padding: 0.65rem 0.8rem;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
.facts th { color: var(--ink-soft); font-weight: 500; width: 40%; }
.facts .sci { font-style: italic; }

.block { margin-bottom: 2rem; }
.block h3 {
  font-size: 1.1rem;
  font-style: italic;
  border-bottom: 2px solid var(--rule);
  padding-bottom: 0.4rem;
}
.block ul { margin: 0.6rem 0 0; padding-left: 1.2rem; }
.block li { margin-bottom: 0.5rem; }
.muted { color: var(--ink-soft); font-style: italic; }

.plant-nav {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--rule);
}
.nav-link { color: var(--link-blue); font-weight: 500; font-size: 0.9rem; }
.nav-link.index {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.75rem;
  color: var(--ink-soft);
}

/* Editorial pass: make the catalog feel like a designed field journal. */
:root {
  --paper: #f7f4ed;
  --paper-deep: #e7e8df;
  --ink: #19241c;
  --ink-soft: #687168;
  --green: #1e5137;
  --green-deep: #102f22;
  --rule: rgba(25, 36, 28, 0.16);
  --blue: #164fc0;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.23;
  background-image: linear-gradient(rgba(25,36,28,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(25,36,28,.025) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(to bottom, black, transparent 75%);
}

.site-header {
  max-width: 1180px;
  min-height: 440px;
  padding: 6.8rem 3rem 4rem;
  text-align: left;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  align-content: end;
  gap: 1.5rem 5rem;
  position: relative;
}
.site-header::after {
  content: "NUPPL / 2026";
  position: absolute;
  top: 2rem;
  right: 3rem;
  color: var(--ink-soft);
  font: 600 .7rem/1 "Work Sans", sans-serif;
  letter-spacing: .16em;
}
.site-header .eyebrow { grid-column: 1 / -1; }
.site-header h1 { font-size: clamp(3.4rem, 8vw, 7rem); letter-spacing: -.04em; max-width: 700px; }
.tagline { margin: 0; max-width: 540px; font-size: 1.02rem; }
#search { align-self: end; justify-self: end; max-width: 290px; border-radius: 0; border: 0; border-bottom: 2px solid var(--green); background: transparent; padding: .85rem 0; }
.hero-copy { position: relative; z-index: 2; animation: rise-in .85s cubic-bezier(.2,.8,.2,1) both; }
.hero-collage { min-height: 330px; position: relative; transform: rotate(2deg); animation: collage-in 1.1s .15s cubic-bezier(.2,.8,.2,1) both; }
.hero-photo { position: absolute; margin: 0; overflow: hidden; background: var(--paper-deep); box-shadow: 0 18px 32px rgba(16,47,34,.16); border: 7px solid var(--paper); opacity: 0; animation: photo-in .75s cubic-bezier(.2,.8,.2,1) forwards; }
.hero-photo img { display: block; width: 100%; height: 100%; object-fit: cover; filter: saturate(.82) contrast(1.05); transition: transform .6s ease, filter .6s ease; }
.hero-photo:hover img { transform: scale(1.08); filter: saturate(1.15) contrast(1.04); }
.hero-photo figcaption { position: absolute; left: .6rem; bottom: .55rem; color: #fff; font-size: .65rem; text-transform: uppercase; letter-spacing: .08em; text-shadow: 0 1px 8px #000; }
.hero-photo-1 { width: 190px; height: 245px; top: 10px; left: 0; transform: rotate(-7deg); animation-delay: .25s; }
.hero-photo-2 { width: 165px; height: 205px; top: 100px; left: 145px; transform: rotate(5deg); animation-delay: .38s; }
.hero-photo-3 { width: 145px; height: 185px; top: 0; right: 5px; transform: rotate(8deg); animation-delay: .51s; }
.hero-photo-4 { width: 160px; height: 205px; bottom: 0; right: 115px; transform: rotate(-5deg); animation-delay: .64s; }
.hero-photo-5 { width: 125px; height: 170px; bottom: 5px; left: 35px; transform: rotate(4deg); animation-delay: .77s; }
.hero-photo-6 { width: 120px; height: 155px; top: 125px; right: 0; transform: rotate(-4deg); animation-delay: .9s; }
@keyframes rise-in { from { opacity: 0; transform: translateY(25px); } to { opacity: 1; transform: translateY(0); } }
@keyframes collage-in { from { opacity: 0; transform: translateX(35px) rotate(8deg); } to { opacity: 1; transform: translateX(0) rotate(2deg); } }
@keyframes photo-in { from { opacity: 0; transform: translateY(24px) rotate(0); } to { opacity: 1; } }

main { max-width: 1180px; padding: 0 3rem 5rem; }
.cat-block { padding: 3.3rem 0; position: relative; }
.cat-block h2 { font-size: 2.6rem; gap: 1rem; }
.cat-count { border-radius: 50%; min-width: 2.4rem; height: 2.4rem; display: inline-grid; place-items: center; padding: 0; font-size: .74rem; }
.index-grid { columns: 4 200px; column-gap: 2.6rem; margin-top: 2rem; }
.index-grid li { margin-bottom: .75rem; }
.index-link { color: var(--blue); font-size: .96rem; padding: .32rem 0; transition: transform .18s ease, color .18s ease; }
.index-link:hover { border: 0; color: var(--green); transform: translateX(6px); }
.index-link .sci { font-size: .72rem; margin-top: .08rem; }

.plant-header { max-width: 1180px; padding: 2.2rem 3rem 1.4rem; position: relative; }
.plant-hero { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(300px, .95fr); height: 440px; border-radius: 14px; background: radial-gradient(circle at 82% 18%, rgba(232,174,91,.38), transparent 24%), linear-gradient(122deg, #173d2a 0%, #2f6844 52%, #b95e31 150%); color: var(--paper); box-shadow: 0 20px 36px rgba(16,47,34,.18); position: relative; overflow: hidden; }
.plant-hero::after { content: ""; position: absolute; width: 360px; height: 360px; border: 1px solid rgba(244,239,228,.25); border-radius: 50%; left: 38%; bottom: -245px; box-shadow: 0 0 0 24px rgba(244,239,228,.035), 0 0 0 48px rgba(244,239,228,.025); pointer-events: none; }
.plant-hero-copy { padding: 2.4rem 2.2rem; align-self: center; position: relative; z-index: 1; }
.plant-hero-copy::after { content: ""; display: block; width: 4.5rem; height: 3px; margin-top: 1.8rem; background: var(--orange); }
.plant-hero-image { min-height: 0; height: 420px; margin: 1rem 1rem 1rem 0; position: relative; border: 8px solid rgba(244,239,228,.88); border-radius: 9px; overflow: hidden; transform: rotate(1.5deg); box-shadow: 0 18px 30px rgba(13,34,22,.28); z-index: 1; }
.plant-hero-image img { display: block; width: 100%; height: 100%; object-fit: cover; }
.plant-hero .eyebrow { color: #c6d8bd; }
.plant-header h1 { color: var(--paper); font-size: clamp(2.8rem, 6vw, 5.6rem); line-height: .94; letter-spacing: -.04em; max-width: 620px; }
.common-alt { max-width: 35rem; font-size: 1.05rem; color: rgba(244,239,228,.72); }
.plant-main { max-width: 1180px; padding: 0 3rem 3rem; }

.gallery { display: block; margin: 0 0 2.25rem; }
.gallery-footer { margin-top: 3.5rem; padding-top: 2.5rem; border-top: 1px solid var(--rule); }
.gallery-heading { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--rule); padding-bottom: .65rem; margin-bottom: 1rem; color: var(--ink-soft); text-transform: uppercase; letter-spacing: .13em; font-size: .7rem; }
.gallery-heading strong { color: var(--green); font-size: .68rem; }
.gallery-grid { display: grid; grid-template-columns: repeat(4, 1fr); grid-auto-rows: 145px; gap: .8rem; }
.gallery-item { margin: 0; position: relative; overflow: hidden; background: var(--paper-deep); border-radius: 8px; }
.gallery-item:first-child { grid-column: span 2; grid-row: span 2; }
.gallery-item img { width: 100%; height: calc(100% - 2rem); object-fit: cover; display: block; filter: saturate(.9) contrast(1.03); transition: transform .5s ease, filter .5s ease; }
.gallery-item:hover img { transform: scale(1.045); filter: saturate(1.1) contrast(1.05); }
.gallery-external { border: 2px solid rgba(30,81,55,.28); }
.gallery-item figcaption { position: static; inset: auto; height: 2rem; display: flex; align-items: center; padding: 0 .65rem; color: var(--ink-soft); background: var(--paper); font-size: .62rem; letter-spacing: .06em; text-transform: uppercase; }
.gallery-empty { border: 1px dashed var(--rule); border-radius: 8px; }

.content-grid { grid-template-columns: 280px 1fr; gap: 2.8rem; align-items: start; }
.facts { background: rgba(255,255,255,.68); border-radius: 10px; border-top: 3px solid var(--green); }
.facts th, .facts td { padding: .85rem .95rem; }
.block { margin-bottom: 2.8rem; }
.block h3 { font-size: 1.45rem; border-bottom: 1px solid var(--rule); padding-bottom: .7rem; }
.block li { margin-bottom: .7rem; }
.plant-nav { max-width: 1180px; padding: 2rem 3rem 5rem; }
.inline-photo { margin: .2rem 0 2.5rem; max-width: 520px; }
.inline-photo img { display: block; width: 100%; max-height: 250px; object-fit: cover; border-radius: 8px; box-shadow: 0 12px 24px rgba(23,48,29,.12); }
.inline-photo figcaption { margin-top: .45rem; color: var(--ink-soft); font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; }

@media (max-width: 760px) {
  .site-header { min-height: 0; padding: 4.5rem 1.4rem 3rem; display: block; }
  .site-header h1 { margin-top: 1.2rem; font-size: 3.3rem; }
  .hero-collage { min-height: 280px; margin: 2.3rem -.4rem 0; transform: scale(.9) rotate(2deg); transform-origin: top center; }
  #search { margin-top: 2rem; max-width: none; width: 100%; }
  main, .plant-main { padding-left: 1.4rem; padding-right: 1.4rem; }
  .plant-header { padding: 2.2rem 1.4rem 1.2rem; }
  .plant-hero { display: block; height: auto; min-height: 0; }
  .plant-hero-copy { padding: 1.5rem 1.25rem 1.7rem; }
  .plant-hero-image { margin: 0 .8rem .8rem; transform: none; }
  .plant-hero-image, .plant-hero-image img { min-height: 0; height: 220px; }
  .plant-hero-image::after { background: linear-gradient(0deg, rgba(18,36,23,.2), transparent 55%); }
  .plant-header h1 { font-size: 3.3rem; margin-top: 1rem; }
  .gallery-grid { grid-template-columns: repeat(2, 1fr); grid-auto-rows: 135px; }
  .gallery-item:first-child { grid-column: span 2; }
  .content-grid { grid-template-columns: 1fr; gap: 2rem; }
  .plant-nav { padding-left: 1.4rem; padding-right: 1.4rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
"""
    with open(os.path.join(DOCS, "assets", "style.css"), "w", encoding="utf-8") as fh:
        fh.write(css)


if __name__ == "__main__":
    build()
