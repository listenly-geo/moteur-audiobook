#!/usr/bin/env python3
"""
Pipeline UNIFIÉ audiobook : analyse GSC → scoring dynamique → proposition des meilleures fiches.
Secret requis : GSC_SERVICE_ACCOUNT_JSON
"""
import os, json, datetime
import requests
from typing import Dict, List

FICHES_DIR = "pages/moteur-audiobook"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"
GSC_DATA_FILE = "data/gsc_data.json"  # Cache local des données GSC

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
SITE = "sc-domain:audiobooklab.fr"

def get_gsc_token():
    """Génère un token OAuth2 depuis la clé du compte de service."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info = json.loads(os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "{}"))
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token

def fetch_gsc_data():
    """Récupère les données de performance réelles depuis GSC."""
    try:
        tok = get_gsc_token()
        url = f"https://www.googleapis.com/webmasters/v3/sites/{requests.utils.quote(SITE, safe='')}/searchAnalytics/query"

        fin = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        debut = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()

        body = {
            "startDate": debut,
            "endDate": fin,
            "dimensions": ["page"],
            "rowLimit": 10000
        }

        r = requests.post(url, headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=60)
        r.raise_for_status()

        data = {}
        for row in r.json().get("rows", []):
            page = row["keys"][0]
            data[page] = {
                "clics": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": round(row.get("ctr", 0), 4),
                "position": round(row.get("position", 0), 1)
            }

        # Sauvegarde le cache
        os.makedirs("data", exist_ok=True)
        with open(GSC_DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✅ GSC: {len(data)} pages analysées")
        return data
    except Exception as e:
        print(f"⚠️  GSC inaccessible: {str(e)[:100]}")
        # Charge le cache si GSC échoue
        if os.path.exists(GSC_DATA_FILE):
            with open(GSC_DATA_FILE) as f:
                return json.load(f)
        return {}

def score_fiche_quality(question: str, gsc_data: Dict, url: str) -> float:
    """Score dynamique basé sur la qualité intrinsèque + performances réelles."""
    q_lower = question.lower()
    score = 5.0

    # Score statique (qualité intrinsèque)
    author_keywords = {
        "contrat": 3, "éditeur": 3, "droits": 3, "agent": 3, "agence": 3,
        "vente": 2, "vendre": 2, "public": 2, "lecteur": 2,
        "publier": 2, "avance": 2, "royalties": 3, "négociation": 3,
        "prix": 2, "coût": 2, "budget": 2,
    }

    weak_keywords = {
        "pourquoi": -1, "philosophie": -2, "universel": -2,
        "actrice": -3, "cinéaste": -3, "retraduction": -3,
    }

    for keyword, points in author_keywords.items():
        if keyword in q_lower:
            score += points

    for keyword, points in weak_keywords.items():
        if keyword in q_lower:
            score += points

    # Bonus si la fiche est déjà indexée et performe bien
    if url in gsc_data:
        perf = gsc_data[url]
        if perf["clics"] > 0:
            score += 5  # Fiche qui produit du trafic = excellente
        elif perf["impressions"] > 10:
            score += 2  # Fiche vue mais pas cliquée = passable

    return max(0, min(10, score))

def load_proposed_history():
    """Charge la liste des URLs déjà proposées."""
    if os.path.exists(PROPOSED_HISTORY_FILE):
        with open(PROPOSED_HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_proposed_history(proposed):
    """Sauvegarde la liste des URLs proposées."""
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed)), f, ensure_ascii=False, indent=2)

def get_best_fiches(gsc_data: Dict) -> tuple:
    """Retourne les 5 meilleures fiches (score >= 6) basé sur l'apprentissage GSC."""

    if not os.path.isdir(FICHES_DIR):
        return [], []

    fiche_files = sorted(
        [f for f in os.listdir(FICHES_DIR) if f.endswith(".html") and f not in ["sitemap.xml", "robots-fragment.txt"]],
        key=lambda f: os.path.getmtime(os.path.join(FICHES_DIR, f)),
        reverse=True
    )

    proposed_history = load_proposed_history()
    to_propose = []
    skipped = []

    for filename in fiche_files:
        slug = filename[:-5]
        url = f"{SITE_BASE_URL}{slug}.html"

        if url not in proposed_history:
            question = slug.replace("-", " ")
            quality_score = score_fiche_quality(question, gsc_data, url)

            if quality_score >= 6:
                to_propose.append({
                    "slug": slug,
                    "url": url,
                    "quality_score": quality_score
                })
            else:
                skipped.append({"url": url, "quality_score": quality_score})

        if len(to_propose) >= 5:
            break

    # Enregistre les fiches proposées + filtrées
    for fiche in to_propose:
        proposed_history.add(fiche["url"])
    for fiche in skipped:
        proposed_history.add(fiche["url"])
    save_proposed_history(proposed_history)

    return to_propose, skipped

def main():
    print("=" * 80)
    print(f"📊 PIPELINE UNIFIÉE AUDIOBOOK - {datetime.date.today().isoformat()}")
    print("=" * 80)

    # 1️⃣ Récupère les données GSC (ce qui performe vraiment)
    print("\n1️⃣ Analyse GSC...")
    gsc_data = fetch_gsc_data()

    # 2️⃣ Propose les meilleures fiches basé sur GSC + qualité
    print("\n2️⃣ Scoring dynamique...")
    fiches, skipped = get_best_fiches(gsc_data)

    # 3️⃣ Affiche les résultats
    if not fiches:
        print("✅ Aucune nouvelle fiche pertinente à proposer.")
        if skipped:
            print(f"⚠️  {len(skipped)} fiche(s) filtrée(s) pour faible qualité.")
        return

    print(f"\n🎯 {len(fiches)} fiche(s) À INDEXER (basé sur GSC + qualité) :\n")

    for i, fiche in enumerate(fiches, 1):
        score = fiche['quality_score']
        emoji = "⭐⭐⭐" if score >= 8 else "⭐⭐" if score >= 7 else "⭐"
        print(f"{i}. {emoji} Score: {score:.1f}/10")
        print(f"   {fiche['url']}")

    if skipped:
        print(f"\n⚠️  {len(skipped)} fiche(s) filtrée(s) pour qualité insuffisante")

    print(f"\n🔍 Lien GSC : https://search.google.com/u/1/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")
    print(f"\n📈 Chaque jour: analyse réelle → meilleure sélection")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Erreur: {str(e)[:300]}")
        exit(1)
