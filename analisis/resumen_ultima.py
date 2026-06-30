"""
resumen_ultima.py

Genera docs/json/resumen_ultima.json con un resumen de la conferencia mañanera
más reciente:
  - temas: términos/frases más DISTINTIVOS del día frente al resto del corpus
    (TF-IDF léxico, sin IA ni dependencias externas).
  - participantes: funcionarios que intervinieron (determinístico) + nº de
    preguntas de prensa.

Ligero: solo stdlib + helpers locales (sin spacy/sklearn), para correr dentro
del workflow del scraper.

Uso:
    python analisis/resumen_ultima.py
"""

import json
import math
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

from parse_corpus import parsear_archivo
from nombres import (normaliza_hablante, clave_merge, categoria_funcionario,
                     _segmento_nombre, _segmento_cargo)

ROOT = Path(__file__).parent.parent
CORPUS_DIR = ROOT / "corpus"
DOCS_JSON = ROOT / "docs" / "json"
OUT = DOCS_JSON / "resumen_ultima.json"

N_TEMAS = 6
WORD_RE = re.compile(r"[a-záéíóúüñ]{3,}")

# Palabras de protocolo/genéricas que no aportan tema (además de las stopwords
# funcionales de stopwords.json).
PROTOCOLO = {
    # Protocolo / muletillas
    "gracias", "buenos", "buenas", "días", "tardes", "noches", "muchas",
    "bueno", "entonces", "ahorita", "ahora", "the", "and", "of", "for",
    "señora", "señor", "parte", "caso", "tema", "temas", "manera", "vamos",
    "aquí", "acá", "allá", "siempre", "cosa", "cosas", "todas", "todos",
    "mismo", "misma", "méxico", "país", "gobierno", "federal", "nacional",
    "general",
    # Palabras de cargo / rol (aparecen en las etiquetas de hablante)
    "presidenta", "presidente", "pregunta", "secretario", "secretaria",
    "subsecretario", "subsecretaria", "director", "directora", "gobernador",
    "gobernadora", "titular", "coordinador", "coordinadora", "fiscal",
    "procurador", "beneficiario", "beneficiaria", "representante", "doctor",
    "doctora", "licenciado", "jefe", "jefa",
    # Anotaciones de la estenografía
    "enlace", "videollamada", "video", "videos", "proyección", "intervención",
    "inaudible", "continúa", "voz", "hombre", "mujer", "audio",
}


def cargar_stopwords() -> set:
    sw = set(PROTOCOLO)
    try:
        sw |= set(json.loads((DOCS_JSON / "stopwords.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    return sw


# ---------------------------------------------------------------------------
# Temas (TF-IDF léxico)
# ---------------------------------------------------------------------------

def _ngramas(tokens: list[str], stop: set) -> set:
    """Unigramas (no stopword) + bigramas de tokens adyacentes no stopword."""
    grams = {t for t in tokens if t not in stop}
    for a, b in zip(tokens, tokens[1:]):
        if a not in stop and b not in stop:
            grams.add(f"{a} {b}")
    return grams


MIN_TF_UNI = 4   # un unigrama debe repetirse bastante para ser "tema"
MIN_TF_BI = 2    # los bigramas (frases) son más informativos: umbral menor


def temas_lexico(textos: list[str], idx: int, stop: set) -> list[str]:
    """Términos distintivos del documento `idx` por TF-IDF contra todo el corpus."""
    n_docs = len(textos)

    # Frecuencia de documento (en cuántas conferencias aparece cada n-grama)
    df = Counter()
    for txt in textos:
        df.update(_ngramas(WORD_RE.findall(txt.lower()), stop))

    # Frecuencia de término en la conferencia objetivo
    toks = WORD_RE.findall(textos[idx].lower())
    tf = Counter(t for t in toks if t not in stop)
    for a, b in zip(toks, toks[1:]):
        if a not in stop and b not in stop:
            tf[f"{a} {b}"] += 1

    score = {}
    for term, c in tf.items():
        es_frase = " " in term
        if df[term] < 1 or c < (MIN_TF_BI if es_frase else MIN_TF_UNI):
            continue
        idf = math.log(n_docs / df[term])
        # Las frases pesan más que las palabras sueltas (leen como temas)
        score[term] = c * idf * (1.4 if es_frase else 1.0)

    # Ranking; preferimos frases y evitamos solapamientos
    ranked = sorted(score, key=lambda t: (-score[t], -len(t)))
    elegidos: list[str] = []
    for term in ranked:
        if len(elegidos) >= N_TEMAS:
            break
        if any(term in e or e in term for e in elegidos):
            continue   # ya cubierto por una frase elegida (o viceversa)
        elegidos.append(term)

    return [t.capitalize() for t in elegidos]


# ---------------------------------------------------------------------------
# Participantes (determinístico)
# ---------------------------------------------------------------------------

def participantes(turnos: list[dict]) -> tuple[list, int]:
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
        lista.append({
            "nombre": _segmento_nombre(canon),
            "cargo": _segmento_cargo(canon),
            "categoria": categoria_funcionario(canon),
            "intervenciones": sum(counts[v] for v in vs),
        })
    lista.sort(key=lambda x: (-x["intervenciones"], x["nombre"]))
    return lista, preguntas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def cuerpo_de(ruta: Path) -> str:
    """Texto de la conferencia sin las 3 líneas de metadata."""
    return "\n".join(ruta.read_text(encoding="utf-8").splitlines()[3:]).strip()


def main():
    archivos = sorted(CORPUS_DIR.glob("*.txt"))
    if not archivos:
        print("Corpus vacío.")
        sys.exit(1)

    ruta = archivos[-1]   # el más reciente (nombres YYYY-MM-DD)
    print(f"Última mañanera: {ruta.name}")

    meta = parsear_archivo(ruta)["meta"]
    turnos = parsear_archivo(ruta)["turnos"]
    if meta.get("incompleto"):
        print("  Aviso: transcripción marcada como incompleta (CONTINÚA…).")

    plist, preguntas = participantes(turnos)

    stop = cargar_stopwords()
    # Excluir del léxico los nombres propios de TODOS los que hablaron ese día
    # (funcionarios, invitados, beneficiarios) para que no salgan como "temas".
    stop |= {"sheinbaum", "claudia", "pardo"}
    for t in turnos:
        if t["tipo"] in ("funcionario", "otro"):
            nom = _segmento_nombre(normaliza_hablante(t["hablante"]))
            stop.update(WORD_RE.findall(nom.lower()))

    textos = [cuerpo_de(p) for p in archivos]
    temas = temas_lexico(textos, len(archivos) - 1, stop)

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
    print(f"  temas: {temas}")


if __name__ == "__main__":
    main()
