"""Descarga ideas (materia prima, nunca se publican) de los subreddits de config.json.

Uso: python reddit_ideas.py
"""
import json
import time
from pathlib import Path

import requests

from claves import clave

RAIZ = Path(__file__).resolve().parent
IDEAS = RAIZ / "ideas"


def token():
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(clave("REDDIT_CLIENT_ID"), clave("REDDIT_CLIENT_SECRET")),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": clave("REDDIT_USER_AGENT")},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def descargar():
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))["reddit"]
    IDEAS.mkdir(exist_ok=True)
    cab = {"Authorization": f"bearer {token()}", "User-Agent": clave("REDDIT_USER_AGENT")}
    nuevas = 0
    for sub, genero in cfg["subreddits"].items():
        r = requests.get(
            f"https://oauth.reddit.com/r/{sub}/top",
            params={"t": cfg["periodo"], "limit": cfg["limite"], "raw_json": 1},
            headers=cab,
            timeout=30,
        )
        r.raise_for_status()
        for hijo in r.json()["data"]["children"]:
            p = hijo["data"]
            texto = (p.get("selftext") or "").strip()
            if p.get("stickied") or texto in ("", "[removed]", "[deleted]"):
                continue
            if p.get("over_18") and not cfg["permitir_nsfw"]:
                continue
            if len(texto.split()) < cfg["min_palabras"]:
                continue
            destino = IDEAS / f"{p['id']}.json"
            if destino.exists():
                continue
            destino.write_text(json.dumps({
                "id": p["id"],
                "subreddit": sub,
                "genero": genero,
                "titulo": p["title"],
                "texto": texto,
                "puntos": p["score"],
                "url": "https://www.reddit.com" + p["permalink"],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            nuevas += 1
        time.sleep(1)  # cortesía con la API
    print(f"Ideas nuevas: {nuevas} (en {IDEAS})")
    return nuevas


if __name__ == "__main__":
    descargar()
