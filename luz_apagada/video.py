"""Monta el vídeo de una historia: fondo, banner, subtítulos quemados, voz + música, miniatura y registro.

Uso: python video.py historias/<id>.json [--vertical] [--estricto] [--segundos N] [--voz-simulada]
"""
import argparse
import csv
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import base

RAIZ = Path(__file__).resolve().parent
FONDOS = RAIZ / "fondos"
SALIDA = RAIZ / "salida"
CFG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
AMARILLO = (255, 194, 26, 255)
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
FUENTES = ["C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]


def ffmpeg(*args, cwd=None):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, args)], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg falló:\n{r.stderr[-1500:]}")


def ruta_fuente():
    for f in [CFG["video"].get("fuente")] + FUENTES:
        if f and Path(f).exists():
            return f
    return None


def fuente(tam):
    f = ruta_fuente()
    return ImageFont.truetype(f, tam) if f else ImageFont.load_default(tam)


# ---------- Fondo ----------

def clips_disponibles(genero):
    for carpeta in (FONDOS / genero, FONDOS / "gameplay", FONDOS):
        clips = sorted(p for p in carpeta.glob("*") if p.suffix.lower() in EXT_VIDEO) if carpeta.is_dir() else []
        if clips:
            return clips
    return []


def comprobar_licencias(clips, estricto):
    registradas = set()
    csv_lic = FONDOS / "licencias.csv"
    if csv_lic.exists():
        with open(csv_lic, encoding="utf-8-sig", newline="") as f:
            for fila in csv.DictReader(f, delimiter=";"):
                if (fila.get("archivo") or "").strip() and (fila.get("licencia") or "").strip():
                    registradas.add(fila["archivo"].strip().replace("\\", "/"))
    faltan = [c for c in clips if c.name not in registradas and c.relative_to(FONDOS).as_posix() not in registradas]
    if faltan:
        print(f"AVISO: {len(faltan)} clip(s) sin licencia registrada en {csv_lic}:")
        for c in faltan:
            print(f"  - {c.relative_to(FONDOS).as_posix()}")
        if estricto:
            sys.exit("--estricto: proceso detenido. Registra los clips (archivo;fuente;licencia;url) o quítalos.")


def construir_fondo(clips, duracion, ancho, alto, carpeta):
    """Concatena trozos aleatorios de 20-40 s sin repetir el mismo clip dos veces seguidas."""
    if not clips:
        img = Image.new("RGB", (ancho, alto))
        d = ImageDraw.Draw(img)
        for y in range(alto):
            k = y / alto
            d.line([(0, y), (ancho, y)], fill=(int(18 + 10 * k), int(14 + 6 * k), int(30 + 18 * k)))
        img.save(carpeta / "_degradado.png")
        return carpeta / "_degradado.png", True
    durs = {c: base.duracion(c) for c in clips}
    vf = (f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
          f"fps=30,setsar=1,format=yuv420p")
    trozos, total, anterior = [], 0.0, None
    while total < duracion + 1:
        opciones = [c for c in clips if c != anterior] or clips
        clip = random.choice(opciones)
        seg = min(random.uniform(20, 40), durs[clip])
        ini = random.uniform(0, max(0, durs[clip] - seg))
        out = carpeta / f"_trozo_{len(trozos):03d}.mp4"
        ffmpeg("-ss", f"{ini:.2f}", "-t", f"{seg:.2f}", "-i", clip, "-an", "-vf", vf,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", out)  # intermedio: calidad media para no llenar el disco
        trozos.append(out)
        total += base.duracion(out)
        anterior = clip
    (carpeta / "_trozos.txt").write_text("".join(f"file '{t.name}'\n" for t in trozos), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", "_trozos.txt", "-c", "copy", "_fondo.mp4", cwd=carpeta)
    for t in trozos + [carpeta / "_trozos.txt"]:
        t.unlink()
    return carpeta / "_fondo.mp4", False


# ---------- Gráficos ----------

def ajustar(draw, texto, ancho_max, tam, max_lineas=3, tam_min=26):
    while True:
        f = fuente(tam)
        lineas, actual = [], ""
        for w in texto.split():
            prueba = f"{actual} {w}".strip()
            if draw.textlength(prueba, font=f) <= ancho_max or not actual:
                actual = prueba
            else:
                lineas.append(actual)
                actual = w
        lineas.append(actual)
        if len(lineas) <= max_lineas or tam <= tam_min:
            return f, lineas[:max_lineas]
        tam -= 4


def crear_banner(gancho, ancho, alto, ruta):
    vertical = alto > ancho
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margen, pad = (60, 36) if vertical else (48, 28)
    top = 140 if vertical else 36
    tam_marca, tam_texto = (44, 74) if vertical else (34, 54)
    f_marca = fuente(tam_marca)
    f_txt, lineas = ajustar(d, gancho.upper(), ancho - 2 * (margen + pad), tam_texto)
    alto_linea = int(f_txt.size * 1.18)
    alto_tarjeta = pad + tam_marca + 18 + alto_linea * len(lineas) + pad
    d.rounded_rectangle([margen, top, ancho - margen, top + alto_tarjeta], radius=28, fill=(10, 10, 14, 175))
    y = top + pad
    marca = "LUZ APAGADA RELATOS"
    d.text(((ancho - d.textlength(marca, font=f_marca)) / 2, y), marca, font=f_marca, fill=AMARILLO)
    y += tam_marca + 18
    for l in lineas:
        d.text(((ancho - d.textlength(l, font=f_txt)) / 2, y), l, font=f_txt, fill="white",
               stroke_width=4, stroke_fill="black")
        y += alto_linea
    img.save(ruta)


def crear_miniatura(gancho, fondo, es_imagen, carpeta):
    ruta_frame = carpeta / "_frame.png"
    if es_imagen:
        shutil.copy(fondo, ruta_frame)
    else:
        ffmpeg("-ss", "3", "-i", fondo, "-frames:v", "1", ruta_frame)
    img = Image.open(ruta_frame).convert("RGB")
    escala = max(1280 / img.width, 720 / img.height)
    img = img.resize((int(img.width * escala + 1), int(img.height * escala + 1)))
    x, y = (img.width - 1280) // 2, (img.height - 720) // 2
    img = img.crop((x, y, x + 1280, y + 720)).convert("RGBA")
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    for yy in range(250, 720):
        dc.line([(0, yy), (1280, yy)], fill=(0, 0, 0, int(235 * (yy - 250) / 470)))
    img = Image.alpha_composite(img, capa)
    d = ImageDraw.Draw(img)
    f, lineas = ajustar(d, gancho.upper(), 1280 - 2 * 60, 84, tam_min=44)
    alto_linea = int(f.size * 1.15)
    yy = 720 - 50 - alto_linea * len(lineas)
    for i, l in enumerate(lineas):
        color = AMARILLO if i == len(lineas) - 1 else "white"
        d.text((60, yy), l, font=f, fill=color, stroke_width=6, stroke_fill="black")
        yy += alto_linea
    img.convert("RGB").save(carpeta / "miniatura.jpg", quality=92)
    ruta_frame.unlink()


# ---------- Principal ----------

def crear_video(ruta_historia, vertical=False, estricto=False, segundos=None, voz_simulada=False):
    h = json.loads(Path(ruta_historia).read_text(encoding="utf-8"))
    ancho, alto = (1080, 1920) if vertical else (1920, 1080)
    carpeta = SALIDA / (h["id"] + ("-vertical" if vertical else ""))
    vcfg = CFG["video"]
    segundos = vcfg["banner_segundos"] if segundos is None else segundos

    clips = clips_disponibles(h["genero"])
    comprobar_licencias(clips, estricto)
    carpeta.mkdir(parents=True, exist_ok=True)
    if not clips:
        print("AVISO: no hay clips en fondos/; se usará un degradado oscuro.")

    print(f"[{h['id']}] voz…")
    voz = CFG["voz"].get(h["genero"], CFG["voz"]["misterio"])
    mp3, palabras = base.sintetizar(h["texto"], voz, CFG["voz"]["velocidad"], carpeta, voz_simulada)
    dur = base.duracion(mp3)
    grupos = base.grupos_subtitulos(palabras)
    base.escribir_srt(grupos, carpeta / "subtitulos.srt")
    nombre_fuente = fuente(10).getname()[0]
    base.escribir_ass(grupos, carpeta / "_subtitulos.ass", ancho, alto, nombre_fuente)

    print(f"[{h['id']}] fondo ({dur / 60:.1f} min)…")
    fondo, es_imagen = construir_fondo(clips, dur, ancho, alto, carpeta)
    crear_banner(h["titulo_portada"], ancho, alto, carpeta / "_banner.png")
    crear_miniatura(h["titulo_portada"], fondo, es_imagen, carpeta)

    entradas = (["-loop", "1", "-framerate", "30"] if es_imagen else []) + ["-i", fondo.name]
    entradas += ["-loop", "1", "-framerate", "30", "-i", "_banner.png", "-i", mp3.name]
    musica = vcfg.get("musica")
    if musica and not Path(musica).is_absolute():
        musica = str(RAIZ / musica)
    activar = f":enable='lte(t,{segundos})'" if segundos else ""
    fontsdir = f":fontsdir='{Path(ruta_fuente()).parent.as_posix()}'" if ruta_fuente() else ""
    filtros = (f"[0:v]vignette=PI/5,eq=brightness=-0.08:saturation=0.8[b];"
               f"[b][1:v]overlay=0:0{activar}[o];[o]subtitles=_subtitulos.ass{fontsdir}[v];"
               f"[2:a]loudnorm=I=-16:TP=-1.5:LRA=11")
    if musica and Path(musica).exists():
        entradas += ["-stream_loop", "-1", "-i", musica]
        filtros += f"[voz];[3:a]volume={vcfg['volumen_musica']}[m];[voz][m]amix=inputs=2:duration=first:normalize=0[a]"
    else:
        if musica:
            print(f"AVISO: no existe la música {musica}; se omite.")
        filtros += "[a]"
    print(f"[{h['id']}] render final…")
    ffmpeg(*entradas, "-filter_complex", filtros, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}",
           "-r", "30", "-c:v", "libx264", "-preset", vcfg["preset"], "-crf", vcfg["crf"], "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "video.mp4", cwd=carpeta)
    for tmp in carpeta.glob("_*"):
        tmp.unlink()
    mp3.unlink()

    meta = {k: h[k] for k in ("titulo", "descripcion", "etiquetas")}
    meta["origen"] = h.get("origen")
    (carpeta / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "metadata.txt").write_text(
        f"TÍTULO:\n{h['titulo']}\n\nDESCRIPCIÓN:\n{h['descripcion']}\n\nETIQUETAS:\n{', '.join(h['etiquetas'])}\n",
        encoding="utf-8")
    reg = base.registrar(RAIZ / CFG["registro"], {
        "id": h["id"], "genero": h["genero"], "formato": "vertical" if vertical else "horizontal",
        "titulo": h["titulo"], "duracion_min": round(dur / 60, 1), "carpeta": str(carpeta)})
    print(f"[{h['id']}] listo: {carpeta} (registro: {reg.name})")
    return carpeta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("historia")
    ap.add_argument("--vertical", action="store_true")
    ap.add_argument("--estricto", action="store_true", help="detener si falta alguna licencia")
    ap.add_argument("--segundos", type=float, help="segundos que se ve el banner (0 = siempre)")
    ap.add_argument("--voz-simulada", action="store_true", help="tono en vez de EdgeTTS (pruebas)")
    a = ap.parse_args()
    crear_video(a.historia, a.vertical, a.estricto, a.segundos, a.voz_simulada)
