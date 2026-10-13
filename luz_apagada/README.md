# Luz Apagada Relatos · pipeline

Requisitos: Python 3.10+, ffmpeg/ffprobe en el PATH, `pip install requests pillow openpyxl edge-tts`.

1. Copia `.env.ejemplo` a `.env` y rellénalo. Comprueba: `python claves.py --comprobar`
2. Clips de fondo en `fondos/<genero>/`, `fondos/gameplay/` o `fondos/`, y cada uno en `fondos/licencias.csv` (`archivo;fuente;licencia;url`). Solo material propio o con licencia; nunca vídeos de otros canales.
3. `python auto.py --cuantas 2 --genero misterio [--vertical] [--estricto] [--sin-reddit]`

Pasos sueltos: `python reddit_ideas.py`, `python reescribir.py ideas/<id>.json`, `python video.py historias/<id>.json [--vertical] [--segundos 5]`.
Pruebas sin gastar API ni voz: añade `--simulado` (auto/reescribir) o `--voz-simulada` (video).

Salida: `salida/<id>[-vertical]/` con video.mp4, miniatura.jpg, subtitulos.srt, metadata.json/.txt, y una fila "pendiente de subir" en `registro.xlsx`.
`base.py` agrupa voz, subtítulos y registro: si ya tienes tus propias funciones para eso, cámbialas ahí.
