#!/usr/bin/env python3
"""
generate_fiches_index.py

Scanne toutes les fiches HTML générées par le moteur audiobook
(pages/moteur-audiobook/*.html) et produit un dashboard interne
(index.html) listant l'historique complet des fiches : date de
génération, question traitée, extrait, lien vers la fiche live.

Ce script est autonome et ne dépend d'aucun dashboard existant.
À lancer après chaque génération de fiche (même logique que
generate_sitemap() dans generate_audiobook_fiches.py) :

    python3 automation/scripts/generate_fiches_index.py

Sortie : pages/moteur-audiobook/dashboard/index.html
"""

import os
import re
import json
from datetime import datetime

FICHES_DIR = "pages/moteur-audiobook"
DASHBOARD_DIR = os.path.join(FICHES_DIR, "dashboard")
OUTPUT_PATH = os.path.join(DASHBOARD_DIR, "index.html")
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook"


def log(msg):
    print(f"[fiches-index] {msg}")


def extract_metadata(path, fname):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    def grab(pattern, default=""):
        m = re.search(pattern, content, re.S)
        return m.group(1).strip() if m else default

    return {
        "slug": fname.replace(".html", ""),
        "headline": grab(r'"headline":\s*"([^"]*)"'),
        "date": grab(r'"datePublished":\s*"([^"]*)"'),
        "description": grab(r'<meta name="description" content="([^"]*)"'),
        "url": grab(r'<link rel="canonical" href="([^"]*)"')
               or f"{SITE_BASE_URL}/{fname}",
    }


def collect_entries():
    if not os.path.isdir(FICHES_DIR):
        log("⚠ Dossier de fiches introuvable, index non généré.")
        return []

    entries = []
    for fname in sorted(os.listdir(FICHES_DIR)):
        if not fname.endswith(".html"):
            continue
        entries.append(extract_metadata(os.path.join(FICHES_DIR, fname), fname))

    # Tri anti-chronologique (fiches les plus récentes en premier)
    entries.sort(key=lambda e: (e["date"], e["slug"]), reverse=True)
    return entries


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Historique des fiches — Moteur Audiobook</title>
<style>
  :root {{
    --bg: #14130f;
    --panel: #1c1a15;
    --panel-border: #2c2820;
    --ink: #ece6d6;
    --ink-dim: #9c9484;
    --ink-faint: #635c4c;
    --amber: #e3b341;
    --amber-dim: #7a5f22;
    --rule: #2c2820;
    --mono: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
    --serif: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
  }}
  a {{ color: inherit; }}

  .topbar {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(20, 19, 15, 0.92);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--rule);
    padding: 20px 32px;
  }}
  .topbar-inner {{
    max-width: 980px;
    margin: 0 auto;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px 24px;
  }}
  .brand {{
    display: flex;
    align-items: baseline;
    gap: 10px;
  }}
  .brand-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--amber);
    display: inline-block;
    box-shadow: 0 0 8px var(--amber);
    align-self: center;
  }}
  h1 {{
    font-family: var(--serif);
    font-weight: 400;
    font-size: 20px;
    letter-spacing: 0.01em;
    margin: 0;
  }}
  .subtitle {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-faint);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .stats {{
    display: flex;
    gap: 28px;
    font-family: var(--mono);
    font-size: 12px;
    color: var(--ink-dim);
  }}
  .stats strong {{
    color: var(--amber);
    font-size: 15px;
    display: block;
    font-weight: 600;
  }}
  .stats span {{
    display: block;
    margin-top: 2px;
  }}

  main {{
    max-width: 980px;
    margin: 0 auto;
    padding: 40px 32px 100px;
  }}

  .search-row {{
    margin-bottom: 28px;
  }}
  .search-row input {{
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--panel-border);
    color: var(--ink);
    font-family: var(--mono);
    font-size: 13px;
    padding: 12px 16px;
    border-radius: 6px;
    outline: none;
    transition: border-color 0.15s ease;
  }}
  .search-row input:focus {{ border-color: var(--amber-dim); }}
  .search-row input::placeholder {{ color: var(--ink-faint); }}

  .ledger {{
    position: relative;
  }}
  .ledger::before {{
    content: "";
    position: absolute;
    left: 5px;
    top: 8px;
    bottom: 8px;
    width: 1px;
    background: var(--rule);
  }}

  .entry {{
    position: relative;
    padding: 0 0 0 32px;
    margin-bottom: 4px;
    border-radius: 8px;
  }}
  .entry::before {{
    content: "";
    position: absolute;
    left: 1px;
    top: 22px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--bg);
    border: 1px solid var(--amber-dim);
  }}
  .entry-inner {{
    display: block;
    text-decoration: none;
    padding: 16px 18px;
    border-radius: 8px;
    border: 1px solid transparent;
    transition: background 0.12s ease, border-color 0.12s ease;
  }}
  .entry-inner:hover {{
    background: var(--panel);
    border-color: var(--panel-border);
  }}
  .entry-inner:hover ~ .entry::before,
  .entry:has(.entry-inner:hover)::before {{
    border-color: var(--amber);
    background: var(--amber);
  }}
  .entry-meta {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-faint);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  }}
  .entry-title {{
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.4;
    color: var(--ink);
    margin-bottom: 6px;
  }}
  .entry-desc {{
    font-family: var(--sans);
    font-size: 13px;
    line-height: 1.5;
    color: var(--ink-dim);
    max-width: 720px;
  }}

  .day-divider {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-faint);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin: 32px 0 8px 32px;
  }}
  .day-divider:first-child {{ margin-top: 0; }}

  .empty {{
    font-family: var(--mono);
    color: var(--ink-faint);
    padding: 60px 0;
    text-align: center;
  }}

  footer {{
    max-width: 980px;
    margin: 0 auto;
    padding: 0 32px 40px;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-faint);
  }}

  @media (max-width: 640px) {{
    .topbar {{ padding: 16px 20px; }}
    main {{ padding: 28px 20px 80px; }}
    .stats {{ gap: 18px; }}
  }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-dot"></span>
        <div>
          <h1>Historique des fiches</h1>
          <div class="subtitle">Moteur Audiobook &middot; AudiobookLab</div>
        </div>
      </div>
      <div class="stats">
        <div><strong>{total}</strong><span>fiches générées</span></div>
        <div><strong>{last_date}</strong><span>dernière génération</span></div>
      </div>
    </div>
  </div>

  <main>
    <div class="search-row">
      <input id="search" type="text" placeholder="Filtrer par mot-clé, thème ou question…" autocomplete="off">
    </div>

    <div class="ledger" id="ledger">
      {entries_html}
    </div>
    <div class="empty" id="empty" style="display:none;">Aucune fiche ne correspond à cette recherche.</div>
  </main>

  <footer>
    Généré automatiquement à partir de {source_dir}/*.html &middot; {generated_at}
  </footer>

  <script>
    const search = document.getElementById('search');
    const entries = Array.from(document.querySelectorAll('.entry'));
    const dividers = Array.from(document.querySelectorAll('.day-divider'));
    const empty = document.getElementById('empty');

    search.addEventListener('input', () => {{
      const q = search.value.trim().toLowerCase();
      let visibleCount = 0;
      entries.forEach(el => {{
        const hay = el.dataset.search || '';
        const match = hay.includes(q);
        el.style.display = match ? '' : 'none';
        if (match) visibleCount++;
      }});
      dividers.forEach(d => {{
        const group = d.nextElementSibling ? d : null;
        // hide divider if no visible entries follow until next divider
        let sib = d.nextElementSibling, anyVisible = false;
        while (sib && !sib.classList.contains('day-divider')) {{
          if (sib.classList.contains('entry') && sib.style.display !== 'none') anyVisible = true;
          sib = sib.nextElementSibling;
        }}
        d.style.display = anyVisible ? '' : 'none';
      }});
      empty.style.display = visibleCount === 0 ? 'block' : 'none';
    }});
  </script>
</body>
</html>
"""

ENTRY_TEMPLATE = """<div class="entry" data-search="{search_blob}">
        <a class="entry-inner" href="{url}" target="_blank" rel="noopener">
          <div class="entry-meta">{date}</div>
          <div class="entry-title">{headline}</div>
          <div class="entry-desc">{description}</div>
        </a>
      </div>"""


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def build_html(entries):
    if not entries:
        body = '<div class="empty">Aucune fiche générée pour le moment.</div>'
        total, last_date = 0, "—"
    else:
        blocks = []
        last_seen_date = None
        for e in entries:
            if e["date"] != last_seen_date:
                blocks.append(f'<div class="day-divider">{esc(e["date"] or "date inconnue")}</div>')
                last_seen_date = e["date"]
            search_blob = esc(f'{e["headline"]} {e["description"]} {e["slug"]}'.lower())
            blocks.append(ENTRY_TEMPLATE.format(
                search_blob=search_blob,
                url=esc(e["url"]),
                date=esc(e["date"] or "—"),
                headline=esc(e["headline"] or e["slug"]),
                description=esc(e["description"]),
            ))
        body = "\n      ".join(blocks)
        total = len(entries)
        last_date = entries[0]["date"] or "—"

    return HTML_TEMPLATE.format(
        total=total,
        last_date=last_date,
        entries_html=body,
        source_dir=FICHES_DIR,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def main():
    entries = collect_entries()
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    html = build_html(entries)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"✅ Index régénéré ({len(entries)} fiches) : {OUTPUT_PATH}")

    # Registre JSON brut, utile pour d'autres consommateurs (ex: moteur trafic)
    json_path = os.path.join(DASHBOARD_DIR, "fiches-index.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    log(f"✅ Registre JSON régénéré : {json_path}")


if __name__ == "__main__":
    main()
