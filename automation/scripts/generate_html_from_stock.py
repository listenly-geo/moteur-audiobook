#!/usr/bin/env python3
"""
Génère les pages HTML des TOP 5 questions du stock podcast.

ZÉRO appel Claude - réutilise données du stock existant:
  • Question (extraite précédemment)
  • Réponse brute (du transcript)
  • Citation (verbatim podcast)
  • Bio expert (validée)

Crée pages HTML prêtes pour indexation Google.
"""

import os, json, re
from datetime import datetime

STOCK_FILE = "automation/state/question_stock.json"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
OUTPUT_DIR = "pages/moteur-audiobook/"

def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def slugify(text):
    """Crée un slug URL-safe."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:80].strip('-')

def escape_html(text):
    """Échappe le HTML pour éviter les injections."""
    if not text:
        return ""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#39;")
    return text

def generate_page_html(question_data):
    """Génère le HTML complet d'une page."""

    question = question_data.get("question", {}).get("question", "")
    answer = question_data.get("question", {}).get("reponse_brute", "")
    citation = question_data.get("question", {}).get("citation", "")
    bio = question_data.get("bio_courte", "")
    guest = question_data.get("guest_name", "")
    episode = question_data.get("episode_title", "")

    # Nettoie et échappe
    question = escape_html(question)
    answer = escape_html(answer)
    citation = escape_html(citation)
    bio = escape_html(bio)
    guest = escape_html(guest)
    episode = escape_html(episode)

    # Génère le titre SEO court
    title_short = question.rstrip("?").strip()
    truncate_words = [" quand ", " si ", " pour ", " en ", " versus ", " ou "]
    for word in truncate_words:
        if word.lower() in title_short.lower():
            title_short = title_short.split(word)[0].strip()
            break

    # HTML complet
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_short}? — AudiobookLab</title>
    <meta name="description" content="Expert insight from {guest} on {title_short.lower()}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f9f9f9;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            font-size: 2em;
            margin-bottom: 30px;
            color: #000;
        }}
        .expert {{
            background: #f0f0f0;
            padding: 20px;
            border-radius: 6px;
            margin-bottom: 30px;
            border-left: 4px solid #2997FF;
        }}
        .expert h3 {{
            margin-bottom: 8px;
            color: #000;
        }}
        .expert p {{
            font-size: 0.95em;
            color: #555;
        }}
        .answer {{
            margin-bottom: 30px;
            font-size: 1.05em;
            line-height: 1.8;
        }}
        blockquote {{
            border-left: 4px solid #2997FF;
            padding-left: 20px;
            margin: 30px 0;
            font-style: italic;
            color: #666;
        }}
        .citation {{
            font-size: 0.9em;
            color: #999;
            margin-top: 10px;
        }}
        .cta {{
            margin-top: 40px;
            padding: 20px;
            background: #2997FF;
            border-radius: 6px;
            text-align: center;
        }}
        .cta a {{
            color: white;
            text-decoration: none;
            font-weight: 600;
            font-size: 1.1em;
        }}
        .cta a:hover {{
            text-decoration: underline;
        }}
        .meta {{
            color: #999;
            font-size: 0.85em;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{question}</h1>

        <div class="expert">
            <h3>{guest}</h3>
            <p>{bio}</p>
            <p style="font-size: 0.85em; margin-top: 10px; color: #999;">Source: {episode}</p>
        </div>

        <div class="answer">
            {answer}
        </div>

        <blockquote>
            {citation}
            <div class="citation">— {guest}</div>
        </blockquote>

        <div class="cta">
            <a href="https://audiobooklab.org/">Transformer ton livre en audiobook</a>
        </div>

        <div class="meta">
            <p>Insight from <strong>{guest}</strong> on <em>{episode}</em></p>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</p>
        </div>
    </div>
</body>
</html>"""

    return html.strip()

def main():
    print("=" * 80)
    print(f"📄 GÉNÉRATION PAGES HTML — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    # Charge le stock
    stock = load_json(STOCK_FILE, [])
    proposed = load_proposed_urls()

    if not stock:
        print("⚠️  Stock vide.")
        return

    print(f"\n🏊 Chargé: {len(stock)} questions du podcast\n")

    # Crée les répertoires
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Génère une page pour chaque question du stock
    created = []
    for q_data in stock:
        question = q_data.get("question", {}).get("question", "")
        guest = q_data.get("guest_name", "")

        if not question:
            continue

        # Génère slug
        slug = slugify(question)
        filename = f"{slug}.html"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Génère HTML
        html = generate_page_html(q_data)

        # Sauvegarde
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        created.append({
            "question": question,
            "guest": guest,
            "filename": filename,
            "url": f"https://audiobooklab.fr/blog-audiobook/{filename}"
        })

        print(f"✅ {filename[:60]}")

    print(f"\n✅ {len(created)} pages créées\n")

    for page in created[:5]:
        print(f"  • {page['question'][:50]}")
        print(f"    → {page['url']}\n")

    print(f"📁 Dossier: {OUTPUT_DIR}")

def load_proposed_urls():
    """Charge les URLs déjà proposées."""
    if not os.path.exists(PROPOSED_HISTORY_FILE):
        return set()
    with open(PROPOSED_HISTORY_FILE) as f:
        data = json.load(f)
    return set(data) if isinstance(data, list) else set()

if __name__ == "__main__":
    main()
