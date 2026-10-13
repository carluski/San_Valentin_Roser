"""Piezas que ya existen en el pipeline del canal: voz EdgeTTS, subtítulos y registro.

Si tu proyecto ya tiene sus propias funciones, sustituye aquí `sintetizar`, `grupos_subtitulos`
y `registrar` por llamadas a ellas; video.py solo depende de estas tres firmas.
"""
import asyncio
import csv
import datetime as dt
import re
import subprocess
import unicodedata
from pathlib import Path

MAX_PALABRAS = 6
MAX_SEG = 2.8
PUNTUACION = ".,;:!?…»\")"


def duracion(ruta):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


# ---------- Voz ----------

async def _edge(texto, voz, velocidad, mp3):
    import edge_tts
    palabras = []
    com = edge_tts.Communicate(texto, voz, rate=velocidad, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for c in com.stream():
            if c["type"] == "audio":
                f.write(c["data"])
            elif c["type"] == "WordBoundary":
                palabras.append((c["offset"] / 1e7, (c["offset"] + c["duration"]) / 1e7, c["text"]))
    return palabras


def _voz_simulada(texto, mp3):
    """Tono suave con tiempos estimados (0.38 s/palabra): solo para pruebas sin red."""
    palabras, t = [], 0.0
    for w in texto.split():
        d = 0.38 + (0.25 if w[-1] in ".!?…" else 0)
        palabras.append((t, t + 0.34, w))
        t += d
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={t + 0.5:.2f}",
                    "-af", "volume=0.05", "-q:a", "6", str(mp3)], check=True)
    return palabras


def sintetizar(texto, voz, velocidad, carpeta, simulado=False):
    """Genera voz.mp3 por párrafos (evita desfases en relatos largos). Devuelve (mp3, [(ini, fin, palabra)])."""
    carpeta = Path(carpeta)
    trozos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    lista, todas, desfase = [], [], 0.0
    for i, trozo in enumerate(trozos):
        mp3 = carpeta / f"_voz_{i:03d}.mp3"
        pal = _voz_simulada(trozo, mp3) if simulado else asyncio.run(_edge(trozo, voz, velocidad, mp3))
        todas += [(a + desfase, b + desfase, w) for a, b, w in pal]
        desfase += duracion(mp3)
        lista.append(mp3)
    (carpeta / "_voz.txt").write_text("".join(f"file '{p.name}'\n" for p in lista), encoding="utf-8")
    salida = carpeta / "voz.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "_voz.txt", "-c", "copy",
                    salida.name], cwd=carpeta, check=True)
    for p in lista + [carpeta / "_voz.txt"]:
        p.unlink()
    return salida, _alinear(texto, todas)


def _norm(w):
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^a-z0-9ñ]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


def _alinear(texto, palabras):
    """Sustituye cada palabra de EdgeTTS por el token original (con su puntuación)."""
    tokens, j, res = texto.split(), 0, []
    for a, b, w in palabras:
        nw = _norm(w)
        for k in range(j, min(j + 6, len(tokens))):
            if nw and nw in _norm(tokens[k]):
                w, j = tokens[k], k + 1
                break
        res.append((a, b, w))
    return res


# ---------- Subtítulos ----------

def grupos_subtitulos(palabras):
    grupos, actual = [], []
    for p in palabras:
        actual.append(p)
        if (len(actual) >= MAX_PALABRAS or p[1] - actual[0][0] >= MAX_SEG or p[2][-1] in PUNTUACION):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    res = [[g[0][0], g[-1][1], " ".join(w for _, _, w in g)] for g in grupos]
    for actual, siguiente in zip(res, res[1:]):  # evita parpadeos entre grupos casi seguidos
        if siguiente[0] - actual[1] < 0.3:
            actual[1] = siguiente[0]
    return [tuple(g) for g in res]


def _t(s, sep):
    h, m = int(s // 3600), int(s % 3600 // 60)
    return f"{h:02d}:{m:02d}:{s % 60:06.3f}".replace(".", sep) if sep == "," else f"{h}:{m:02d}:{s % 60:05.2f}"


def escribir_srt(grupos, ruta):
    Path(ruta).write_text("\n".join(f"{i}\n{_t(a, ',')} --> {_t(b, ',')}\n{t}\n" for i, (a, b, t) in
                                    enumerate(grupos, 1)), encoding="utf-8")


def escribir_ass(grupos, ruta, ancho, alto, fuente="DejaVu Sans"):
    vertical = alto > ancho
    tam, margen = (68, 520) if vertical else (58, 90)
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ancho}
PlayResY: {alto}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{fuente},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,2,80,80,{margen},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = [f"Dialogue: 0,{_t(a, '.')},{_t(b, '.')},Base,,0,0,0,,{t.replace(chr(10), ' ')}" for a, b, t in grupos]
    Path(ruta).write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")


# ---------- Registro (Excel de control) ----------

COLUMNAS = ["fecha", "id", "genero", "formato", "titulo", "duracion_min", "carpeta", "estado"]


def registrar(ruta, fila):
    ruta = Path(ruta)
    try:
        import openpyxl
    except ImportError:
        ruta = ruta.with_suffix(".csv")
    fila = {"fecha": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "estado": "pendiente de subir", **fila}
    if ruta.suffix == ".csv":
        nuevo = not ruta.exists()
        with open(ruta, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, COLUMNAS, delimiter=";")
            if nuevo:
                w.writeheader()
            w.writerow({k: fila.get(k, "") for k in COLUMNAS})
        return ruta
    if ruta.exists():
        libro = openpyxl.load_workbook(ruta)
        hoja = libro.active
    else:
        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.title = "Videos"
        hoja.append(COLUMNAS)
    hoja.append([fila.get(k, "") for k in COLUMNAS])
    libro.save(ruta)
    return ruta
