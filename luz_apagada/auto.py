"""Orquestador: Reddit -> historia original -> vídeo.

Uso: python auto.py [--cuantas 1] [--genero misterio|romance] [--vertical] [--estricto] [--sin-reddit] [--simulado]
"""
import argparse
import json
from pathlib import Path

import reescribir
import video

RAIZ = Path(__file__).resolve().parent
IDEAS = RAIZ / "ideas"
USADAS = IDEAS / "usadas.txt"


def ideas_pendientes(genero):
    usadas = set(USADAS.read_text(encoding="utf-8").split()) if USADAS.exists() else set()
    ideas = [json.loads(p.read_text(encoding="utf-8")) for p in IDEAS.glob("*.json")]
    ideas = [i for i in ideas if i["id"] not in usadas and (not genero or i.get("genero") == genero)]
    return sorted(ideas, key=lambda i: i["puntos"], reverse=True)


def marcar_usada(id_):
    with open(USADAS, "a", encoding="utf-8") as f:
        f.write(id_ + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuantas", type=int, default=1)
    ap.add_argument("--genero", choices=["misterio", "romance"])
    ap.add_argument("--vertical", action="store_true")
    ap.add_argument("--estricto", action="store_true")
    ap.add_argument("--sin-reddit", action="store_true", help="usar solo las ideas ya descargadas")
    ap.add_argument("--simulado", action="store_true", help="sin API ni EdgeTTS (pruebas)")
    a = ap.parse_args()

    if not a.sin_reddit:
        import reddit_ideas
        reddit_ideas.descargar()
    IDEAS.mkdir(exist_ok=True)
    pendientes = ideas_pendientes(a.genero)[:a.cuantas]
    if not pendientes:
        print("No hay ideas nuevas.")
        return
    llm = reescribir.llm_simulado if a.simulado else None
    for idea in pendientes:
        genero = a.genero or idea.get("genero", "misterio")
        if a.estricto:  # comprobar licencias ANTES de gastar API
            video.comprobar_licencias(video.clips_disponibles(genero), True)
        historia = reescribir.crear_historia(IDEAS / f"{idea['id']}.json", a.genero, llm)
        marcar_usada(idea["id"])  # también si se descarta, para no volver a gastar API en ella
        if historia:
            video.crear_video(historia, a.vertical, a.estricto, voz_simulada=a.simulado)


if __name__ == "__main__":
    main()
