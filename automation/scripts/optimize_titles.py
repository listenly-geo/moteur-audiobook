#!/usr/bin/env python3
"""
Optimize fiche titles pour audiobook : court + accrocheur + SEO.

Prend:
  - question_stock.json (questions auteurs)
  - keyword_planner.json (volumes Google Ads)

Produit:
  - data/optimized_titles.json avec titres courts (55-60 char) scores

Strategie:
  - Titre court et direct (pas de question)
  - Inclure mot-cle haut volume si pertinent
  - Fortes de "comment", "guide", "pourquoi", "conseil", "secret"
"""
import os, json, re

QUESTION_FILE = "automation/state/question_stock.json"
KEYWORD_FILE = "data/keyword_planner.json"
OUT = "data/optimized_titles.json"

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def short_title(question_text, author_name=None, volume=None):
    """Genere un titre court (55-60 char) a partir d'une question."""
    q = question_text.lower().strip()

    # Patterns pour extraire le concept clé
    if "vivre de" in q or "revenu" in q or "gagner" in q:
        return f"Vivre de sa plume : les vrais chiffres" if not author_name else f"{author_name}: vivre de sa plume"

    if "audiobook" in q or "audio" in q:
        return "Audiobook : transformer son livre en revenu"

    if "négocier" in q or "contrat" in q or "éditeur" in q:
        return "Négocier avec un éditeur : le guide"

    if "productiv" in q or "combien" in q and "pages" in q:
        return "Productivité d'auteur : la vérité"

    if "première" in q or "publier" in q or "premier" in q:
        return "Publier son premier livre : étapes clés"

    if "droits" in q or "vente" in q or "royalties" in q:
        return "Droits d'auteur : maximiser ses revenus"

    if "style" in q or "écriture" in q or "voice" in q:
        return "Style d'écriture : trouver sa voix"

    if "marketing" in q or "promotion" in q:
        return "Marketing d'auteur : sans budget"

    # Default: extraire les 3 premiers mots significatifs
    words = [w for w in q.split() if len(w) > 3][:3]
    default = " ".join(words).title() if words else "Guide d'auteur"
    return f"{default}: conseils experts"

def score_title(title, volume, relevance_audiobook=0.5):
    """Score un titre sur : longueur (idéale 55-60) + volume + audiobook."""
    len_score = 10 if 50 <= len(title) <= 65 else max(0, 10 - abs(len(title) - 57.5) / 5)
    volume_score = min(10, (volume or 100) / 100) if volume else 5
    audiobook_score = 10 if any(w in title.lower() for w in ["audiobook", "revenu", "vivre"]) else 6

    final = (len_score * 0.3 + volume_score * 0.4 + audiobook_score * 0.3)
    return round(final, 1)

def main():
    questions = load_json(QUESTION_FILE)
    keywords = load_json(KEYWORD_FILE) or {"idees": []}

    # Indexer volumes par requete
    volumes = {idea.get("requete", ""): idea.get("volume_mensuel_moyen", 0)
               for idea in keywords.get("idees", [])}

    optimized = []
    for q_data in questions:
        q_text = q_data.get("question", {}).get("question", "")
        author = q_data.get("guest_name", "")
        slug = q_data.get("slug", "")

        # Volume pour cette question
        vol = volumes.get(q_text, 100)

        # Titre court
        title = short_title(q_text, author, vol)
        score = score_title(title, vol, 0.7)

        optimized.append({
            "slug": slug,
            "question": q_text,
            "author": author,
            "title_optimized": title,
            "title_length": len(title),
            "volume_mensuel": vol,
            "score": score
        })

    # Trier par score
    optimized.sort(key=lambda x: -x["score"])

    # Sauvegarder
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(optimized, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(optimized)} titres optimisés")
    print("\nTop 5 :")
    for i, item in enumerate(optimized[:5], 1):
        print(f"{i}. [{item['score']:.1f}] {item['title_optimized']} ({item['title_length']} char, {item['volume_mensuel']} vol)")

if __name__ == "__main__":
    main()
