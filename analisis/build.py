"""
build.py

Pipeline de análisis del corpus de mañaneras.
Lee analisis/turns.json (o lo genera si no existe) y produce los JSON
que alimentan la app web en docs/json/.

Uso:
    python analisis/build.py

Salidas en docs/json/:
    corpus_stats.json       estadísticas por conferencia y hablante
    word_freq_monthly.json  top-50 lemas de la presidenta por mes
    tfidf_monthly.json      top-20 términos TF-IDF distintivos por mes
    topics.json             LDA 10 tópicos + distribución por conferencia
    speakers.json           top funcionarios y ratios de voz
    kwic.json               Key Word In Context para top-200 términos
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import nltk
import spacy
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
TURNS_JSON = Path(__file__).parent / "turns.json"
DOCS_JSON = ROOT / "docs" / "json"
DOCS_JSON.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Stopwords en español (NLTK + extensión manual)
# ---------------------------------------------------------------------------

nltk.download("stopwords", quiet=True)
from nltk.corpus import stopwords as nltk_sw

STOPWORDS = set(nltk_sw.words("spanish")) | {
    # Protocolo de conferencia
    "gracias", "buenas", "buenos", "días", "tardes", "noches", "adelante",
    "claro", "sí", "no", "pues", "también", "entonces", "así", "ver",
    # Pronombres / artículos / conectores frecuentes no filtrados por NLTK
    "ir", "ser", "estar", "haber", "tener", "hacer", "decir", "poder",
    "deber", "querer", "venir", "dar", "pasar", "llegar", "seguir",
    "México", "méxico", "país", "año", "años", "día", "días", "mes",
    "presidenta", "presidente", "gobierno", "federal",
    # Ruido de transcripción
    "continúa", "inicia", "finaliza", "proyección", "video", "enlace",
    "videollamada", "inaudible", "intervención",
}

# ---------------------------------------------------------------------------
# Carga de modelo y turns
# ---------------------------------------------------------------------------

def cargar_turns() -> list[dict]:
    if not TURNS_JSON.exists():
        print("turns.json no existe; ejecutando parse_corpus.py primero...")
        import subprocess, sys
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "parse_corpus.py")], check=True
        )
    return json.loads(TURNS_JSON.read_text(encoding="utf-8"))


def get_nlp():
    try:
        return spacy.load("es_core_news_sm", disable=["parser", "ner"])
    except OSError:
        print("Modelo es_core_news_sm no encontrado. Instálalo con:")
        print("  python -m spacy download es_core_news_sm")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Preprocesamiento
# ---------------------------------------------------------------------------

BATCH_SIZE = 100


def lematizar_textos(textos: list[str], nlp) -> list[list[str]]:
    """Devuelve lista de listas de lemas (sustantivos, verbos, adjetivos, adverbios)."""
    POS_VALIDOS = {"NOUN", "VERB", "ADJ", "ADV"}
    resultados = []
    for doc in nlp.pipe(textos, batch_size=BATCH_SIZE):
        lemas = [
            tok.lemma_.lower()
            for tok in doc
            if tok.pos_ in POS_VALIDOS
            and not tok.is_stop
            and not tok.is_punct
            and len(tok.lemma_) > 2
            and tok.lemma_.lower() not in STOPWORDS
            and tok.lemma_.isalpha()
        ]
        resultados.append(lemas)
    return resultados


# ---------------------------------------------------------------------------
# Corpus stats (por conferencia)
# ---------------------------------------------------------------------------

def build_corpus_stats(turns: list[dict]) -> dict:
    """
    Devuelve dict con:
      - por_fecha: {fecha: {presidenta_words, pregunta_turns, funcionario_turns, total_turns}}
      - meses: lista de meses únicos
    """
    por_fecha = defaultdict(lambda: {
        "presidenta_words": 0,
        "pregunta_turns": 0,
        "funcionario_turns": 0,
        "otro_turns": 0,
        "presidenta_turns": 0,
        "total_words": 0,
    })

    for t in turns:
        fecha = t["fecha"]
        palabras = len(t["texto"].split())
        tipo = t["tipo"]
        por_fecha[fecha]["total_words"] += palabras
        if tipo == "presidenta":
            por_fecha[fecha]["presidenta_words"] += palabras
            por_fecha[fecha]["presidenta_turns"] += 1
        elif tipo == "pregunta":
            por_fecha[fecha]["pregunta_turns"] += 1
        elif tipo == "funcionario":
            por_fecha[fecha]["funcionario_turns"] += 1
        else:
            por_fecha[fecha]["otro_turns"] += 1

    fechas_sorted = sorted(por_fecha.keys())
    meses = sorted({f[:7] for f in fechas_sorted})

    return {
        "por_fecha": {f: por_fecha[f] for f in fechas_sorted},
        "meses": meses,
        "fecha_inicio": fechas_sorted[0] if fechas_sorted else "",
        "fecha_fin": fechas_sorted[-1] if fechas_sorted else "",
        "total_conferencias": len(fechas_sorted),
    }


# ---------------------------------------------------------------------------
# Frecuencias mensuales
# ---------------------------------------------------------------------------

def build_word_freq_monthly(turns_pres: list[dict], nlp) -> dict:
    """Top-50 lemas de la presidenta por mes."""
    por_mes = defaultdict(list)
    for t in turns_pres:
        mes = t["fecha"][:7]
        por_mes[mes].append(t["texto"])

    resultado = {}
    meses = sorted(por_mes.keys())
    total = len(meses)
    for i, mes in enumerate(meses, 1):
        print(f"  Frecuencias {mes} ({i}/{total})...", end="\r")
        textos = por_mes[mes]
        lemas_mes = []
        for lemas in lematizar_textos(textos, nlp):
            lemas_mes.extend(lemas)
        freq = Counter(lemas_mes)
        resultado[mes] = dict(freq.most_common(50))

    print()
    return resultado


# ---------------------------------------------------------------------------
# TF-IDF mensual
# ---------------------------------------------------------------------------

def build_tfidf_monthly(turns_pres: list[dict]) -> dict:
    """Top-20 términos TF-IDF distintivos por mes."""
    por_mes = defaultdict(list)
    for t in turns_pres:
        mes = t["fecha"][:7]
        por_mes[mes].append(t["texto"])

    meses = sorted(por_mes.keys())
    docs = [" ".join(por_mes[mes]) for mes in meses]

    sw_list = list(STOPWORDS)
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words=sw_list,
        ngram_range=(1, 2),
        min_df=2,
        token_pattern=r"[a-záéíóúüñ]{3,}",
    )
    matrix = vectorizer.fit_transform(docs)
    vocab = vectorizer.get_feature_names_out()

    resultado = {}
    for i, mes in enumerate(meses):
        row = matrix[i].toarray()[0]
        top_idx = row.argsort()[-20:][::-1]
        resultado[mes] = [
            {"termino": vocab[j], "score": round(float(row[j]), 4)}
            for j in top_idx if row[j] > 0
        ]

    return resultado


# ---------------------------------------------------------------------------
# Topic modeling (LDA)
# ---------------------------------------------------------------------------

N_TOPICS = 10
N_TOP_WORDS = 12


def build_topics(turns_pres: list[dict]) -> dict:
    """LDA con 10 tópicos. Devuelve labels y distribución por fecha."""
    textos = [t["texto"] for t in turns_pres]
    fechas = [t["fecha"] for t in turns_pres]

    sw_list = list(STOPWORDS)
    vectorizer = CountVectorizer(
        max_features=3000,
        stop_words=sw_list,
        token_pattern=r"[a-záéíóúüñ]{3,}",
        min_df=5,
    )
    dtm = vectorizer.fit_transform(textos)
    vocab = vectorizer.get_feature_names_out()

    print(f"  Entrenando LDA ({N_TOPICS} tópicos)...")
    lda = LatentDirichletAllocation(
        n_components=N_TOPICS,
        random_state=42,
        max_iter=20,
        learning_method="batch",
    )
    doc_topics = lda.fit_transform(dtm)

    # Labels: top palabras de cada tópico
    topic_labels = []
    for comp in lda.components_:
        top_idx = comp.argsort()[-N_TOP_WORDS:][::-1]
        topic_labels.append([vocab[i] for i in top_idx])

    # Distribución por fecha (promedio de turnos por conferencia)
    dist_por_fecha = defaultdict(lambda: [0.0] * N_TOPICS)
    count_por_fecha = defaultdict(int)
    for i, fecha in enumerate(fechas):
        dist = doc_topics[i].tolist()
        for j in range(N_TOPICS):
            dist_por_fecha[fecha][j] += dist[j]
        count_por_fecha[fecha] += 1

    dist_normalizada = {}
    for fecha, vec in dist_por_fecha.items():
        n = count_por_fecha[fecha]
        dist_normalizada[fecha] = [round(v / n, 4) for v in vec]

    # Distribución mensual (promedio de conferencias del mes)
    dist_por_mes = defaultdict(lambda: [0.0] * N_TOPICS)
    count_por_mes = defaultdict(int)
    for fecha, vec in dist_normalizada.items():
        mes = fecha[:7]
        for j in range(N_TOPICS):
            dist_por_mes[mes][j] += vec[j]
        count_por_mes[mes] += 1

    dist_mes_norm = {}
    for mes, vec in dist_por_mes.items():
        n = count_por_mes[mes]
        dist_mes_norm[mes] = [round(v / n, 4) for v in vec]

    return {
        "n_topics": N_TOPICS,
        "topic_labels": topic_labels,
        "por_fecha": {f: v for f, v in sorted(dist_normalizada.items())},
        "por_mes": {m: v for m, v in sorted(dist_mes_norm.items())},
    }


# ---------------------------------------------------------------------------
# Encuadre (framing lexicons)
# ---------------------------------------------------------------------------

FRAMES = {
    "nosotros": ["nosotros", "nuestro", "nuestra", "nuestros", "nuestras",
                 "pueblo", "juntos", "juntas", "colectivo", "comunidad"],
    "adversario": ["ellos", "oposición", "adversario", "adversaria",
                   "manipulación", "desinformación", "fake", "calumnia",
                   "mentira", "ataque"],
    "crisis": ["crisis", "problema", "riesgo", "emergencia", "conflicto",
               "desafío", "dificultad", "amenaza", "peligro", "preocupación"],
    "logro": ["avance", "logro", "resultado", "oportunidad", "beneficio",
              "éxito", "progreso", "meta", "objetivo", "alcanzar"],
    "ciencia": ["datos", "evidencia", "científico", "científica", "estudio",
                "análisis", "investigación", "indicador", "medición", "cifra"],
}

FRAMES_SETS = {k: set(v) for k, v in FRAMES.items()}


def build_framing(turns_any: list[dict]) -> dict:
    """Ratio mensual de cada lexicón de encuadre (ocurrencias / total palabras).
    Acepta cualquier lista de turnos (presidenta o todos)."""
    por_mes: dict[str, dict] = defaultdict(lambda: {k: 0 for k in FRAMES} | {"total": 0})

    for t in turns_any:
        mes = t["fecha"][:7]
        palabras = re.findall(r"[a-záéíóúüñ]+", t["texto"].lower())
        por_mes[mes]["total"] += len(palabras)
        for word in palabras:
            for frame, lexicon in FRAMES_SETS.items():
                if word in lexicon:
                    por_mes[mes][frame] += 1

    resultado = {}
    for mes in sorted(por_mes.keys()):
        total = por_mes[mes]["total"]
        if total == 0:
            continue
        resultado[mes] = {
            frame: round(por_mes[mes][frame] / total * 1000, 3)  # por mil
            for frame in FRAMES
        }

    return {"frames": list(FRAMES.keys()), "por_mes": resultado}


# ---------------------------------------------------------------------------
# Speakers / participación
# ---------------------------------------------------------------------------

def build_speakers(turns: list[dict]) -> dict:
    """Top funcionarios, ratios de voz por mes, y fechas de aparición por actor."""
    func_counter = Counter()
    func_fechas: dict[str, list] = defaultdict(list)

    for t in turns:
        if t["tipo"] == "funcionario":
            func_counter[t["hablante"]] += 1
            func_fechas[t["hablante"]].append(t["fecha"])

    top_nombres = [n for n, _ in func_counter.most_common(25)]
    top_funcionarios = [
        {"nombre": nombre, "apariciones": func_counter[nombre]}
        for nombre in top_nombres
    ]
    # Una entrada por turno (sin deduplicar fechas): así la gráfica temporal
    # suma los mismos turnos que el total mostrado en la lista.
    actor_fechas = {nombre: sorted(func_fechas[nombre]) for nombre in top_nombres}

    # Ratio de palabras por tipo por mes
    por_mes: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for t in turns:
        mes = t["fecha"][:7]
        palabras = len(t["texto"].split())
        por_mes[mes][t["tipo"]] += palabras

    ratio_por_mes = {}
    for mes in sorted(por_mes.keys()):
        total = sum(por_mes[mes].values())
        if total == 0:
            continue
        ratio_por_mes[mes] = {
            tipo: round(words / total * 100, 1)
            for tipo, words in por_mes[mes].items()
        }

    return {
        "top_funcionarios": top_funcionarios,
        "actor_fechas": actor_fechas,
        "ratio_palabras_por_mes": ratio_por_mes,
    }


# ---------------------------------------------------------------------------
# KWIC (Key Word In Context)
# ---------------------------------------------------------------------------

KWIC_WINDOW = 60   # caracteres a cada lado de la palabra
MAX_KWIC_PER_WORD = 80
TOP_KWIC_WORDS = 200


TOKEN_RE = re.compile(r"[a-záéíóúüñ]{4,}")


def build_kwic(turns_pres: list[dict]) -> dict:
    """
    Indexa por FORMA DE SUPERFICIE (la palabra tal como aparece en el texto,
    no su lema), para que el usuario pueda buscar "mujeres", "niños", etc. y
    obtenga resultados completos. Toma las 200 formas más frecuentes (≥4 letras,
    sin stopwords) y guarda hasta 80 ejemplos en contexto por cada una.
    """
    # 1ª pasada: contar formas de superficie en los turnos de la presidenta
    freq_superficie = Counter()
    for t in turns_pres:
        for tok in TOKEN_RE.findall(t["texto"].lower()):
            if tok not in STOPWORDS:
                freq_superficie[tok] += 1

    top_words = set(w for w, _ in freq_superficie.most_common(TOP_KWIC_WORDS))
    fragmentos_por_word: dict[str, list] = {w: [] for w in top_words}

    # 2ª pasada: extraer contextos
    for t in turns_pres:
        texto = t["texto"]
        texto_lower = texto.lower()
        # palabras candidatas presentes en este turno (evita recorrer las 200)
        presentes = top_words.intersection(TOKEN_RE.findall(texto_lower))
        for word in presentes:
            if len(fragmentos_por_word[word]) >= MAX_KWIC_PER_WORD:
                continue
            for m in re.finditer(r"\b" + re.escape(word) + r"\b", texto_lower):
                start = max(0, m.start() - KWIC_WINDOW)
                end = min(len(texto), m.end() + KWIC_WINDOW)
                fragmentos_por_word[word].append({
                    "fecha": t["fecha"],
                    "ctx": ("…" if start > 0 else "") + texto[start:end] + ("…" if end < len(texto) else ""),
                })
                if len(fragmentos_por_word[word]) >= MAX_KWIC_PER_WORD:
                    break

    return fragmentos_por_word


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Cargando turns.json...")
    turns = cargar_turns()
    turns_pres = [t for t in turns if t["tipo"] == "presidenta"]
    print(f"  Total turnos: {len(turns):,} | Presidenta: {len(turns_pres):,}")

    print("\n[1/6] Estadísticas de corpus...")
    corpus_stats = build_corpus_stats(turns)
    (DOCS_JSON / "corpus_stats.json").write_text(
        json.dumps(corpus_stats, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → corpus_stats.json ({corpus_stats['total_conferencias']} conferencias)")

    print("\n[2/6] Cargando spaCy...")
    nlp = get_nlp()

    print("\n[3/6] Frecuencias mensuales...")
    word_freq = build_word_freq_monthly(turns_pres, nlp)
    (DOCS_JSON / "word_freq_monthly.json").write_text(
        json.dumps(word_freq, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → word_freq_monthly.json ({len(word_freq)} meses)")

    print("\n[4/6] TF-IDF mensual...")
    tfidf = build_tfidf_monthly(turns_pres)
    (DOCS_JSON / "tfidf_monthly.json").write_text(
        json.dumps(tfidf, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → tfidf_monthly.json ({len(tfidf)} meses)")

    print("\n[5/6] Topic modeling (LDA)...")
    topics = build_topics(turns_pres)
    (DOCS_JSON / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → topics.json ({topics['n_topics']} tópicos, {len(topics['por_fecha'])} fechas)")

    print("\n[6/6] Speakers + encuadre + KWIC...")
    speakers = build_speakers(turns)
    framing_pres  = build_framing(turns_pres)
    framing_total = build_framing(turns)
    speakers["framing_presidenta"] = framing_pres
    speakers["framing_total"]      = framing_total

    (DOCS_JSON / "speakers.json").write_text(
        json.dumps(speakers, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → speakers.json (con actor_fechas y framing presidenta+total)")

    kwic = build_kwic(turns_pres)
    (DOCS_JSON / "kwic.json").write_text(
        json.dumps(kwic, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  → kwic.json ({len(kwic)} términos)")

    print("\n✓ Pipeline completado.")
    sizes = {p.name: f"{p.stat().st_size // 1024} KB" for p in DOCS_JSON.glob("*.json")}
    for name, size in sorted(sizes.items()):
        print(f"  {name}: {size}")


if __name__ == "__main__":
    main()
