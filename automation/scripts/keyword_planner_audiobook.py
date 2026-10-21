#!/usr/bin/env python3
"""
Connecteur Google Keyword Planner (Google Ads API) pour moteur audiobook.

Ce qu'il fait : pour une liste de sujets ou de questions auteurs, demande a Google Ads
les volumes de recherche mensuels (fourchettes) et les idees proches.
Le resultat sert a scorer et trier les fiches auteur par pertinence + trafic potentiel.

Secrets attendus (GitHub Actions secrets, memes noms ici) :
  GOOGLE_ADS_CLIENT_ID         identifiant client OAuth
  GOOGLE_ADS_CLIENT_SECRET     secret client OAuth
  GOOGLE_ADS_REFRESH_TOKEN     jeton de rafraichissement OAuth du compte Google Ads
  GOOGLE_ADS_CUSTOMER_ID       identifiant client Google Ads (10 chiffres, sans tirets)
  GOOGLE_ADS_DEVELOPER_TOKEN  (optionnel) token développeur
  GOOGLE_ADS_LOGIN_CUSTOMER_ID (optionnel) identifiant du compte manager

Sans ces secrets, le script ecrit l'etat « non connecte » et ne fait rien d'autre.
Usage : python3 automation/scripts/keyword_planner_audiobook.py "question ou sujet 1" "sujet 2" ...
"""
import os, sys, json, datetime, urllib.request, urllib.parse, urllib.error

API_VERSION = "v26"
OUT = os.environ.get("KP_OUT") or "data/keyword_planner.json"
TOKEN_URL = "https://oauth2.googleapis.com/token"
LANG = "1005"   # français
GEO = "2250"    # France


def secrets_ok():
    # Verifier que les secrets OAuth sont presentes
    need = ["GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CUSTOMER_ID"]
    return [k for k in need if not os.environ.get(k)]


def access_token():
    """Genere un token d'acces OAuth depuis Google Ads."""
    data = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as r:
        return json.loads(r.read())["access_token"]


def generate_ideas(seeds, token):
    """Demande a Google Ads les volumes et competitivite pour une liste de mots-cles."""
    cid = os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{cid}:generateKeywordIdeas"
    body = {
        "language": f"languageConstants/{LANG}",
        "geoTargetConstants": [f"geoTargetConstants/{GEO}"],
        "keywordPlanNetwork": "GOOGLE_SEARCH",
        "keywordSeed": {"keywords": seeds[:20]},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
        headers["developer-token"] = os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]
    if os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        headers["login-customer-id"] = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"].replace("-", "")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    out = []
    for idea in res.get("results", []):
        m = idea.get("keywordIdeaMetrics", {})
        out.append({
            "requete": idea.get("text"),
            "volume_mensuel_moyen": int(m.get("avgMonthlySearches", 0) or 0),
            "concurrence": m.get("competition", "UNSPECIFIED"),
        })
    return out


def write_state(state):
    """Sauvegarde l'etat (connecte/erreur/non connecte) en JSON."""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(state, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    seeds = [a.strip() for a in sys.argv[1:] if a.strip()]
    now = datetime.datetime.utcnow().isoformat(timespec="minutes") + "Z"
    missing = secrets_ok()
    if missing:
        write_state({"statut": "non connecte", "manque": missing, "date": now})
        print("Keyword Planner audiobook : non connecte. Secrets manquants : " + ", ".join(missing))
        return
    if not seeds:
        print("Keyword Planner audiobook : connecte, aucune requete a tester.")
        return
    try:
        ideas = generate_ideas(seeds, access_token())
        write_state({"statut": "connecte", "date": now, "graines": seeds, "idees": ideas})
        print(f"Keyword Planner audiobook : {len(ideas)} idees pour {len(seeds)} graines.")
    except urllib.error.HTTPError as e:
        write_state({"statut": "erreur", "code": e.code, "date": now, "detail": e.read()[:1500].decode("utf-8", "ignore")})
        print(f"Keyword Planner audiobook : erreur {e.code}. Voir {OUT}.")


if __name__ == "__main__":
    main()
