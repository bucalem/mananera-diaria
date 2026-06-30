"""
resumen_ultima.py

Genera docs/json/resumen_ultima.json con un resumen de la conferencia mañanera
más reciente:
  - temas: temas principales (vía Claude API, modelo Haiku) — requiere
    ANTHROPIC_API_KEY; si no está, se omiten los temas (el resto se genera igual).
  - participantes: funcionarios que intervinieron (determinístico) + nº de
    preguntas de prensa.

Es ligero (solo stdlib + helpers locales): no usa spacy/sklearn, para correr
dentro del workflow del scraper.

Uso:
    python analisis/resumen_ultima.py
"""

import json
import os
import re
import ssl
import sys
from pathlib import Path
from collections import Counter, defaultdict

from parse_corpus import parsear_archivo
from nombres import (normaliza_hablante, clave_merge, categoria_funcionario,
                     _segmento_nombre, _segmento_cargo)

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

import urllib.request

ROOT = Path(__file__).parent.parent
CORPUS_DIR = ROOT / "corpus"
OUT = ROOT / "docs" / "json" / "resumen_ultima.json"

MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
MAX_CHARS = 120_000   # tope de transcripción enviada al modelo


# ---------------------------------------------------------------------------
# Participantes (determinístico)
# ---------------------------------------------------------------------------

def participantes(turnos: list[dict]) -> tuple[list, int]:
    """Funcionarios que intervinieron (fusionando variantes del día) y número
    de preguntas de prensa."""
    counts = Counter()
    variantes = defaultdict(list)
    preguntas = 0

    for t in turnos:
        if t["tipo"] == "funcionario":
            nom = normaliza_hablante(t["hablante"])
            counts[nom] += 1
            variantes[clave_merge(nom)].append(nom)
        elif t["tipo"] == "pregunta":
            preguntas += 1

    lista = []
    for vs in variantes.values():
        canon = max(vs, key=lambda v: counts[v])
        total = sum(counts[v] for v in vs)
        lista.append({
            "nombre": _segmento_nombre(canon),
            "cargo": _segmento_cargo(canon),
            "categoria": categoria_funcionario(canon),
            "intervenciones": total,
        })
    lista.sort(key=lambda x: (-x["intervenciones"], x["nombre"]))
    return lista, preguntas


# ---------------------------------------------------------------------------
# Temas (Claude API)
# ---------------------------------------------------------------------------

def temas_con_claude(texto: str, fecha: str) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  Sin ANTHROPIC_API_KEY; se omiten los temas.")
        return []

    prompt = (
        f"Eres analista político. Resume los TEMAS PRINCIPALES de esta "
        f"conferencia de prensa matutina ('mañanera') de la presidencia de "
        f"México del {fecha}.\n\n"
        f"Devuelve EXCLUSIVAMENTE un JSON válido con la forma:\n"
        f'{{"temas": ["...", "..."]}}\n\n'
        f"Reglas:\n"
        f"- Entre 4 y 6 temas; cada uno una frase breve (máx. ~14 palabras) en español.\n"
        f"- Enfócate en los asuntos sustantivos presentados y discutidos.\n"
        f"- Agrupa las preguntas de prensa por asunto; no listes preguntas sueltas.\n"
        f"- No agregues texto fuera del JSON.\n\n"
        f"Transcripción:\n{texto[:MAX_CHARS]}"
    )
    body = {
        "model": MODEL,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        ANTHROPIC_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        salida = data["content"][0]["text"]
        m = re.search(r"\{.*\}", salida, re.DOTALL)
        temas = json.loads(m.group(0))["temas"]
        return [str(t).strip() for t in temas if str(t).strip()]
    except Exception as e:
        print(f"  Error con Claude API: {e}")
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    archivos = sorted(CORPUS_DIR.glob("*.txt"))
    if not archivos:
        print("Corpus vacío.")
        sys.exit(1)
    ruta = archivos[-1]   # el más reciente (nombres YYYY-MM-DD)
    print(f"Última mañanera: {ruta.name}")

    res = parsear_archivo(ruta)
    meta, turnos = res["meta"], res["turnos"]

    if meta.get("incompleto"):
        print("  Aviso: la transcripción está marcada como incompleta (CONTINÚA…).")

    plist, preguntas = participantes(turnos)
    # texto = todo menos las 3 líneas de metadata
    cuerpo = "\n".join(ruta.read_text(encoding="utf-8").splitlines()[3:]).strip()
    temas = temas_con_claude(cuerpo, meta["fecha"])

    salida = {
        "fecha": meta["fecha"],
        "titulo": meta["titulo"],
        "url": meta["url"],
        "incompleto": meta.get("incompleto", False),
        "n_preguntas": preguntas,
        "temas": temas,
        "participantes": plist,
    }
    OUT.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {OUT.name}: {len(temas)} temas, {len(plist)} funcionarios, {preguntas} preguntas")


if __name__ == "__main__":
    main()
