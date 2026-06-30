"""
parse_corpus.py

Lee todos los .txt del corpus y los convierte en una lista estructurada
de turnos clasificados por tipo de hablante.

Uso:
    python analisis/parse_corpus.py          # imprime resumen y guarda turns.json
    python analisis/parse_corpus.py --check  # solo verifica, no guarda

Salida: analisis/turns.json (usado por build.py)
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
OUTPUT = Path(__file__).parent / "turns.json"

# ---------------------------------------------------------------------------
# Patrones de clasificación
# ---------------------------------------------------------------------------

PRESIDENTA_RE = re.compile(
    r"^(PRESIDENTA DE MÉXICO,\s*CLAUDIA SHEINBAUM PARDO)\s*:\s*(.*)", re.DOTALL
)
PREGUNTA_RE = re.compile(r"^(PREGUNTA)\s*:\s*(.*)", re.DOTALL)
INTERVENCION_RE = re.compile(r"^(INTERVENCIÓN[^:]*)\s*:\s*(.*)", re.DOTALL)
VOZ_RE = re.compile(r"^(VOZ\s+(?:HOMBRE|MUJER)[^:]*)\s*:\s*(.*)", re.DOTALL)

# Cargos que clasifican como funcionario
CARGO_KEYWORDS = (
    "SECRETARI",
    "DIRECTOR",
    "GOBERNADOR",
    "GOBERNADORA",
    "TITULAR",
    "JEFE DE GOBIERNO",
    "JEFA DE GOBIERNO",
    "SUBSECRETARI",
    "COORDINADOR",
    "COORDINADORA",
    "COMISIONADO",
    "FISCAL",
    "PROCURADOR",
    "PRESIDENTE MUNICIPAL",
    "PRESIDENTA MUNICIPAL",
    "SENADOR",
    "DIPUTADO",
    "EMBAJADOR",
    "CÓNSUL",
    "RECTOR",
    "DIRECTORA",
    "BENEFICIARI",
    "REPRESENTANTE",
)

# Patrón genérico para cualquier hablante con formato NOMBRE/CARGO: texto
# El identificador está en mayúsculas y puede incluir comas, espacios y paréntesis
SPEAKER_RE = re.compile(
    r"^([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ0-9\s,\.\-\(\)]+?)\s*:\s+(.*)", re.DOTALL
)

# Acotaciones/anotaciones (líneas entre paréntesis sin hablante)
ANNOTATION_RE = re.compile(r"^\(.*\)$|^—.*—$|^—000—$")

# Palabras de protocolo a excluir del análisis textual (no del parser)
PROTOCOL_WORDS = {
    "gracias", "buenos días", "buenas tardes", "buenas noches",
    "adelante", "con mucho gusto",
}


def clasificar_hablante(identificador: str) -> str:
    id_upper = identificador.upper()
    if "PRESIDENTA DE MÉXICO" in id_upper and "SHEINBAUM" in id_upper:
        return "presidenta"
    if id_upper.strip() == "PREGUNTA":
        return "pregunta"
    if id_upper.startswith("INTERVENCIÓN") or id_upper.startswith("VOZ "):
        return "otro"
    for kw in CARGO_KEYWORDS:
        if kw in id_upper:
            return "funcionario"
    return "otro"


def parsear_archivo(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()

    meta = {"url": "", "fecha": "", "titulo": "", "incompleto": False}
    turnos = []

    # Extraer metadata de las primeras líneas
    for ln in lines[:5]:
        if ln.startswith("URL:"):
            meta["url"] = ln[4:].strip()
        elif ln.startswith("Fecha:"):
            meta["fecha"] = ln[6:].strip()
        elif ln.startswith("Título:"):
            meta["titulo"] = ln[7:].strip()

    if "(CONTINÚA…)" in path.read_text(encoding="utf-8"):
        meta["incompleto"] = True

    # Reconstruir turnos: cada línea con "IDENTIFICADOR: texto" inicia un turno;
    # las líneas siguientes sin ese patrón son continuación del mismo turno.
    turno_actual = None
    idx = 0

    for raw in lines[3:]:  # saltar metadata
        line = raw.strip()
        if not line:
            continue

        # Marcador de fin de transcripción
        if line == "—000—":
            break

        # Acotaciones puras
        if ANNOTATION_RE.match(line):
            if turno_actual:
                turno_actual["texto"] += f" {line}"
            continue

        # Intentar match de hablante
        m = SPEAKER_RE.match(line)
        if m:
            candidato = m.group(1).strip()
            texto = m.group(2).strip()
            # Rechazar si el candidato es muy corto (siglas) o contiene minúsculas
            # (probable que sea texto normal con dos puntos, ej: "hora: 10:00")
            if len(candidato) >= 4 and candidato == candidato.upper():
                if turno_actual:
                    turnos.append(turno_actual)
                tipo = clasificar_hablante(candidato)
                turno_actual = {
                    "fecha": meta["fecha"],
                    "turno": idx,
                    "tipo": tipo,
                    "hablante": candidato,
                    "texto": texto,
                }
                idx += 1
                continue

        # Continuación del turno actual
        if turno_actual:
            turno_actual["texto"] += " " + line

    if turno_actual:
        turnos.append(turno_actual)

    return {"meta": meta, "turnos": turnos}


def parsear_corpus() -> list[dict]:
    archivos = sorted(CORPUS_DIR.glob("*.txt"))
    todos_turnos = []
    stats = defaultdict(int)

    for path in archivos:
        resultado = parsear_archivo(path)
        for t in resultado["turnos"]:
            todos_turnos.append(t)
            stats[t["tipo"]] += 1

    return todos_turnos, stats


def main():
    solo_check = "--check" in sys.argv

    print(f"Parseando {len(list(CORPUS_DIR.glob('*.txt')))} archivos...")
    turnos, stats = parsear_corpus()

    print(f"\nTotal turnos: {len(turnos):,}")
    for tipo, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {tipo:15s}: {count:,}")

    fechas = [t["fecha"] for t in turnos if t["fecha"]]
    if fechas:
        print(f"\nRango: {min(fechas)} → {max(fechas)}")

    # Muestra de turnos de la presidenta
    pres = [t for t in turnos if t["tipo"] == "presidenta"]
    print(f"\nMuestra de turno presidenta:")
    if pres:
        t = pres[5]
        print(f"  Fecha: {t['fecha']}")
        print(f"  Texto: {t['texto'][:200]}...")

    if not solo_check:
        OUTPUT.write_text(json.dumps(turnos, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nGuardado → {OUTPUT}")


if __name__ == "__main__":
    main()
