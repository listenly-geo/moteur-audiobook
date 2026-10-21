#!/usr/bin/env python3
"""
Analyse quotidienne audiobook : récupère les données GSC et propose les fiches à indexer.
Secret requis : GSC_SERVICE_ACCOUNT_JSON (clé du compte de service Google)
"""
import os, json, datetime
import requests
from typing import List, Dict

SITE = "sc-domain:audiobooklab.fr"
OUT = "data/gsc"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

def token():
    """Génère un token OAuth2 depuis la clé du compte de service."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info = json.loads(os.environ["GSC_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token

def query(tok, dims, start, end):
    """Récupère les données de Search Console."""
    url = f"https://www.googleapis.com/webmasters/v3/sites/{requests.utils.quote(SITE, safe='')}/searchAnalytics/query"
    rows = []
    offset = 0
    while True:
        body = {
            "startDate": start,
            "endDate": end,
            "dimensions": dims,
            "rowLimit": 25000,
            "startRow": offset
        }
        r = requests.post(url, headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=60)
        r.raise_for_status()
        batch = r.json().get("rows", [])
        rows += batch
        if len(batch) < 25000:
            break
        offset += 25000
    return rows

def save(name, data):
    """Sauvegarde les données en JSON."""
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def analyze_indexation():
    """Analyse l'état d'indexation des fiches proposées."""
    tok = token()
    fin = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    debut = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()

    # Récupère les pages indexées
    pages_raw = query(tok, ["page"], debut, fin)
    pages = []
    for row in pages_raw:
        pages.append({
            "url": row["keys"][0],
            "clics": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0), 4),
            "position": round(row.get("position", 0), 1)
        })

    # Récupère les requêtes qui envoient du trafic
    queries_raw = query(tok, ["query"], debut, fin)
    queries = []
    for row in queries_raw:
        queries.append({
            "requete": row["keys"][0],
            "clics": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0), 4),
            "position": round(row.get("position", 0), 1)
        })

    # Trie et sauvegarde
    pages = sorted(pages, key=lambda x: -x["clics"])
    queries = sorted(queries, key=lambda x: -x["clics"])

    save("pages", pages)
    save("queries", queries)

    # Résumé
    summary = {
        "date": datetime.date.today().isoformat(),
        "periode": [debut, fin],
        "pages_indexees": len(pages),
        "total_clics": sum(p["clics"] for p in pages),
        "total_impressions": sum(p["impressions"] for p in pages),
        "top_requete": queries[0] if queries else None,
        "top_page": pages[0] if pages else None
    }

    save("summary", summary)

    print(f"✅ {len(pages)} pages indexées")
    print(f"📊 {summary['total_clics']} clics totaux")
    print(f"🔍 Top requête: {summary['top_requete']['requete'] if summary['top_requete'] else 'N/A'}")

    return summary

if __name__ == "__main__":
    if not os.environ.get("GSC_SERVICE_ACCOUNT_JSON"):
        print("❌ Secret GSC_SERVICE_ACCOUNT_JSON absent")
        save("erreur", {"date": datetime.date.today().isoformat(), "erreur": "clé GSC manquante"})
        exit(1)

    try:
        analyze_indexation()
    except Exception as e:
        print(f"❌ Erreur: {str(e)[:300]}")
        save("erreur", {"date": datetime.date.today().isoformat(), "erreur": str(e)[:500]})
