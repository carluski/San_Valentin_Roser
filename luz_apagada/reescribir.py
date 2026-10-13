"""Crea una historia ORIGINAL a partir de la premisa de una idea (no traduce ni parafrasea).

Uso: python reescribir.py ideas/<id>.json [--genero misterio|romance] [--simulado]
"""
import argparse
import json
import random
import re
import unicodedata
from pathlib import Path

import requests

from claves import clave

RAIZ = Path(__file__).resolve().parent
HISTORIAS = RAIZ / "historias"
CFG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
PALABRAS_ESCENA = 600

SISTEMA = (
    "Eres guionista de 'Luz Apagada Relatos', un canal de relatos narrados de misterio y romance. "
    "Escribes en español de España, en primera persona, con prosa oral y cinematográfica pensada para escucharse. "
    "El texto de referencia solo sirve para extraer una premisa y un conflicto emocional: está prohibido traducirlo, "
    "parafrasearlo o reutilizar sus personajes, nombres, lugares, hechos concretos o giros."
)


# ---------- API ----------

def llamar_claude(prompt, max_tokens):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": clave("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": CFG["modelo"], "max_tokens": max_tokens, "system": SISTEMA,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300,
    )
    if not r.ok:
        raise RuntimeError(f"API {r.status_code}: {r.text[:300]} (ejecuta: python claves.py --comprobar)")
    return "".join(b.get("text", "") for b in r.json()["content"]).strip()


def extraer_json(texto):
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini < 0 or fin < 0:
        raise ValueError("La respuesta no contiene JSON")
    return json.loads(texto[ini:fin + 1])


def limpiar_prosa(t):
    t = re.sub(r"^\s*(#+|\*\*|[-*] )", "", t, flags=re.M)
    t = t.replace("**", "").replace("__", "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ---------- Generación ----------

def pedir_esquema(idea, genero, n, llm, aviso=""):
    prompt = f"""Texto de referencia (SOLO para extraer premisa y conflicto emocional):
<<<
{idea['titulo']}
{idea['texto'][:6000]}
>>>

1. Extrae en una frase la premisa y el conflicto emocional de fondo.
2. Inventa una historia NUEVA de {genero} con otros personajes, nombres españoles, lugares de España, hechos y giro final distintos.
{aviso}
Devuelve SOLO un JSON válido con estas claves:
- "premisa_nueva": 2-3 frases.
- "gancho": frase de 12 a 18 palabras, en primera persona, que abre la historia y engancha desde el primer segundo.
- "titulo_youtube": máximo 90 caracteres, explicativo, que dé ganas de ver el vídeo entero (sin clickbait falso).
- "descripcion": 2-3 frases para YouTube, sin spoilers del giro.
- "etiquetas": lista de 3 etiquetas.
- "escenas": lista de exactamente {n} objetos {{"titulo": ..., "resumen": ...}}; la última escena termina con un cierre potente o un cliffhanger."""
    for _ in range(2):
        e = extraer_json(llm(prompt, 3000))
        e["escenas"] = e["escenas"][:n]
        nw = len(e["gancho"].split())
        if 12 <= nw <= 18 and len(e["titulo_youtube"]) <= 90 and len(e["escenas"]) == n:
            return e
        prompt += f"\n\nCORRIGE: el gancho tenía {nw} palabras, el título {len(e['titulo_youtube'])} caracteres y había {len(e['escenas'])} escenas."
    e["titulo_youtube"] = e["titulo_youtube"][:90].rstrip()
    return e


def escribir_escenas(esquema, genero, llm):
    partes = []
    for i, esc in enumerate(esquema["escenas"]):
        previo = partes[-1][-600:] if partes else ""
        inicio = (f'Empieza EXACTAMENTE con esta frase: "{esquema["gancho"]}"' if i == 0
                  else f"Continúa sin repetir desde este final de la escena anterior:\n<<<{previo}>>>")
        prompt = f"""Esquema de la historia ({genero}):
{json.dumps(esquema, ensure_ascii=False, indent=1)}

Escribe la escena {i + 1} de {len(esquema['escenas'])}: "{esc['titulo']}" — {esc['resumen']}
Unas {PALABRAS_ESCENA} palabras, primera persona, español de España, prosa continua para narrar en voz alta.
Sin títulos, sin markdown, sin listas, sin acotaciones. {inicio}"""
        texto = limpiar_prosa(llm(prompt, 2000))
        if i == 0 and not texto.startswith(esquema["gancho"]):
            texto = esquema["gancho"] + " " + texto
        partes.append(texto)
    return "\n\n".join(partes)


# ---------- Originalidad ----------

def normalizar(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ']+", t)


def ngramas(palabras, n=5):
    return [tuple(palabras[i:i + n]) for i in range(len(palabras) - n + 1)]


NO_NOMBRES = {"I", "I'm", "I've", "I'd", "I'll", "OP", "TL", "DR", "TLDR", "Edit", "Update", "Reddit", "AITA",
              "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "God", "Mom", "Dad"}


def nombres_propios(texto):
    """Palabras capitalizadas que no inician frase."""
    res = set()
    for m in re.finditer(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})\b", texto):
        ini = texto[:m.start()].rstrip()
        if ini and ini[-1] not in ".!?¡¿\"«—:" and m.group(1) not in NO_NOMBRES:
            res.add(m.group(1))
    return res


def originalidad(original, nuevo):
    orig = set(ngramas(normalizar(original)))
    nuevos = ngramas(normalizar(nuevo))
    solape = 100 * sum(g in orig for g in nuevos) / max(1, len(nuevos))
    rep = sorted(nombres_propios(original) & set(re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", nuevo)))
    return round(solape, 2), rep


# ---------- Simulación (sin API) ----------

def llm_simulado(prompt, max_tokens):
    rnd = random.Random(len(prompt))
    if "Devuelve SOLO un JSON" in prompt:
        n = int(re.search(r"exactamente (\d+) objetos", prompt).group(1))
        return json.dumps({
            "premisa_nueva": "Una restauradora de Cuenca descubre que el piso heredado de su abuela guarda una carta que nadie debía leer.",
            "gancho": "La noche que heredé el piso de mi abuela, alguien ya había dormido en mi cama.",
            "titulo_youtube": "Heredé el piso de mi abuela y descubrí que alguien seguía viviendo dentro",
            "descripcion": "Lucía vuelve a Cuenca para vaciar un piso que lleva años cerrado. Lo que encuentra cambia todo lo que creía saber de su familia.",
            "etiquetas": ["relatos de misterio", "historias narradas", "luz apagada relatos"],
            "escenas": [{"titulo": f"Escena {i + 1}", "resumen": "Avanza el misterio."} for i in range(n)],
        }, ensure_ascii=False)
    frases = ["Subí la escalera de piedra contando los peldaños como hacía de niña.",
              "El olor a cera vieja me devolvió veranos que creía olvidados.",
              "Nadie en el barrio quiso mirarme a los ojos cuando pregunté por la vecina del tercero.",
              "Encontré la llave dentro de una lata de membrillo, envuelta en papel de periódico.",
              "Mi hermano Tomás dejó de contestar al teléfono justo aquella tarde.",
              "La radio del salón se encendió sola a las tres y diez, como cada noche.",
              "Entendí que el silencio de mi abuela había sido una forma de protegerme."]
    texto = " ".join(rnd.choice(frases) for _ in range(PALABRAS_ESCENA // 12))
    m = re.search(r'EXACTAMENTE con esta frase: "([^"]+)"', prompt)
    return (m.group(1) + " " + texto) if m else texto


# ---------- Principal ----------

def crear_historia(ruta_idea, genero=None, llm=None):
    llm = llm or llamar_claude
    idea = json.loads(Path(ruta_idea).read_text(encoding="utf-8"))
    genero = genero or idea.get("genero", "misterio")
    n = max(1, round(CFG["palabras_objetivo"] / PALABRAS_ESCENA))
    aviso = ""
    for intento in (1, 2):
        esquema = pedir_esquema(idea, genero, n, llm, aviso)
        texto = escribir_escenas(esquema, genero, llm)
        solape, rep = originalidad(idea["titulo"] + "\n" + idea["texto"], texto)
        print(f"[{idea['id']}] intento {intento}: solape {solape} %, nombres repetidos {rep}")
        if solape <= CFG["max_solape_pct"] and len(rep) <= CFG["max_nombres_repetidos"]:
            break
        aviso = (f"ATENCIÓN: un borrador anterior se parecía demasiado al original (solape {solape} %, "
                 f"nombres repetidos {rep}). Cambia por completo personajes, nombres, escenarios y frases.")
    else:
        print(f"[{idea['id']}] DESCARTADA: no supera el control de originalidad.")
        HISTORIAS.mkdir(exist_ok=True)
        with open(HISTORIAS / "descartadas.log", "a", encoding="utf-8") as f:
            f.write(f"{idea['id']}\t{solape}\t{rep}\t{idea['url']}\n")
        return None
    HISTORIAS.mkdir(exist_ok=True)
    historia = {
        "id": idea["id"],
        "genero": genero,
        "titulo_portada": esquema["gancho"],
        "titulo": esquema["titulo_youtube"],
        "descripcion": esquema["descripcion"],
        "etiquetas": esquema["etiquetas"][:3],
        "premisa": esquema["premisa_nueva"],
        "texto": texto,
        "origen": {"url": idea["url"], "solape_pct": solape, "nombres_repetidos": rep},
    }
    destino = HISTORIAS / f"{idea['id']}.json"
    destino.write_text(json.dumps(historia, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{idea['id']}] historia guardada: {destino} ({len(texto.split())} palabras)")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("idea")
    ap.add_argument("--genero", choices=["misterio", "romance"])
    ap.add_argument("--simulado", action="store_true", help="no llama a la API (pruebas)")
    a = ap.parse_args()
    crear_historia(a.idea, a.genero, llm_simulado if a.simulado else None)
