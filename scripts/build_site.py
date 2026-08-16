#!/usr/bin/env python3
"""Generates the static NUPPL-style flora catalog site into ./docs from the raw
plant folders (TREES/HERBS/SHRUBS/GRASS). Re-run after editing any .txt file
or adding photos; it fully regenerates docs/ each time."""
import os
import re
import shutil
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

CATEGORIES = [
    ("TREES", "Trees", "tree"),
    ("HERBS", "Herbs", "herb"),
    ("SHRUBS", "Shrubs", "shrub"),
    ("GRASS", "Grasses", "grass"),
]

IMG_EXTS = (".jpg", ".jpeg", ".png")


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def clean_name(folder_name):
    # collapse double spaces / stray parens spacing used in the raw folder names
    name = re.sub(r"\s+", " ", folder_name).strip()
    return name


HEADING_RULES = [
    ("habitat", "habitat"),
    ("growth form", "habitat"),
    ("features", "habitat"),
    ("economic importance", "importance"),
    ("economic & medicinal importance", "importance"),
    ("economic and medicinal importance", "importance"),
    ("medicinal importance", "importance"),
    ("uses & importance", "importance"),
    ("ecological importance", "importance"),
    ("importance", "importance"),
]

SKIP_HEADING_STARTS = (
    "probable identification",
    "name & scientific",
    "name and scientific",
)


def parse_txt(text):
    data = {"common_name": None, "scientific_name": None, "family": None, "ptype": None}
    sections = {"habitat": [], "importance": [], "other": []}
    current = "other"

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
                "importance": sections["importance"],
                "other": sections["other"],
                "images": copied_imgs,
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
  <p class="eyebrow">Field Survey &middot; Raw Data Handover</p>
  <h1>The Green Register</h1>
  <p class="tagline">A working catalog of {total} campus &amp; local species &mdash; trees, shrubs, herbs and grasses &mdash; documented for the flora magazine layout.</p>
  <input id="search" type="search" placeholder="Search the register by name..." autocomplete="off">
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
    gallery = ""
    if plant["images"]:
        figs = "\n".join(
            f'      <figure><img src="../{src}" alt="{esc(plant["display_name"])} field photo {i+1}" loading="lazy"></figure>'
            for i, src in enumerate(plant["images"])
        )
        gallery = f'<div class="gallery">\n{figs}\n    </div>'
    else:
        gallery = '<div class="gallery gallery-empty"><p>No field photo on file yet.</p></div>'

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
    importance_html = render_list(plant["importance"]) or "<p class=\"muted\">Importance notes pending.</p>"
    other_html = f'<section class="block"><h3>Field Notes</h3>{render_list(plant["other"])}</section>' if plant["other"] else ""

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
  <p class="eyebrow">{esc(plant['category_label'])} Specimen</p>
  <h1>{esc(plant['display_name'])}</h1>
  {f'<p class="common-alt">Also known as: {esc(plant["common_name"])}</p>' if plant["common_name"] and plant["common_name"] != plant["display_name"] else ''}
</header>
<main class="plant-main">
  {gallery}
  <div class="content-grid">
    <div class="col-facts">
      {facts_table}
    </div>
    <div class="col-text">
      <section class="block">
        <h3>Habitat &amp; Growing Conditions</h3>
        {habitat_html}
      </section>
      <section class="block">
        <h3>Ecological &amp; Economic Importance</h3>
        {importance_html}
      </section>
      {other_html}
    </div>
  </div>
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
"""
    with open(os.path.join(DOCS, "assets", "style.css"), "w", encoding="utf-8") as fh:
        fh.write(css)


if __name__ == "__main__":
    build()
