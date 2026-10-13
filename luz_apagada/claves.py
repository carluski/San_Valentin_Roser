"""Lectura de claves desde .env (las variables del sistema tienen prioridad).

Uso: python claves.py --comprobar
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENV = RAIZ / ".env"
CLAVES = ("ANTHROPIC_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")


def leer_env(ruta=ENV):
    datos = {}
    if not ruta.exists():
        return datos
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        k = k.strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].strip()
        datos[k] = v
    return datos


def clave(nombre, obligatoria=True):
    valor = os.environ.get(nombre) or leer_env().get(nombre, "")
    if obligatoria and not valor:
        raise SystemExit(f"Falta {nombre}: añádela al .env ({ENV}) o como variable del sistema.")
    return valor


def enmascarar(v):
    return v[:7] + "…" + v[-4:] if len(v) > 11 else "(demasiado corta)"


PISTAS = {
    401: "key inválida o revocada: cópiala de nuevo desde console.anthropic.com",
    403: "la key no tiene permiso para este recurso/modelo",
    404: "modelo mal escrito o no disponible: revisa 'modelo' en config.json",
    429: "sin saldo o límite de uso alcanzado: revisa Billing/Limits en la consola",
}


def comprobar():
    import json
    import requests
    print(f".env: {'encontrado' if ENV.exists() else 'NO existe'} ({ENV})")
    key = os.environ.get("ANTHROPIC_API_KEY") or leer_env().get("ANTHROPIC_API_KEY", "")
    origen = "variable del sistema" if os.environ.get("ANTHROPIC_API_KEY") else ".env"
    if not key:
        print("ANTHROPIC_API_KEY: NO detectada")
        return 1
    print(f"ANTHROPIC_API_KEY: {enmascarar(key)} (desde {origen})")
    if not key.startswith("sk-ant-"):
        print("  AVISO: no empieza por 'sk-ant-'; probablemente no es una key de Anthropic.")
    for n in CLAVES[1:]:
        print(f"{n}: {'detectada' if clave(n, False) else 'no detectada'}")
    modelo = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))["modelo"]
    print(f"Llamada mínima a la API con el modelo {modelo}…")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": modelo, "max_tokens": 1, "messages": [{"role": "user", "content": "ok"}]},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"  ERROR de red: {e}")
        return 1
    if r.ok:
        print("  OK: la API responde.")
        return 0
    print(f"  ERROR HTTP {r.status_code}: {PISTAS.get(r.status_code, 'error inesperado')}")
    print(f"  Respuesta: {r.text[:300]}")
    return 1


if __name__ == "__main__":
    if "--comprobar" in sys.argv:
        sys.exit(comprobar())
    print(__doc__)
