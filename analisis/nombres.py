"""
nombres.py

Helpers puros (sin dependencias pesadas) para normalizar y clasificar nombres
de funcionarios. Lo comparten build.py (análisis completo) y resumen_ultima.py
(resumen ligero en CI), para tener una sola fuente de verdad.
"""

import re
import unicodedata

TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "Y", "SAN"}
HONORIFICOS = {"DOCTOR", "DOCTORA", "DR", "DRA", "LICENCIADO", "LICENCIADA",
               "LIC", "MAESTRO", "MAESTRA", "MTRO", "MTRA", "INGENIERO", "ING",
               "GENERAL", "ALMIRANTE", "CONTRALMIRANTE", "C"}
# Raíces de cargo: si el texto empieza con una de éstas, el formato es
# "CARGO, NOMBRE"; si no, es el invertido "NOMBRE, CARGO".
CARGO_STEMS = ("SECRETARI", "SUBSECRETARI", "DIRECTOR", "SUBDIRECTOR",
               "GOBERNADOR", "JEFE DE GOBIERNO", "JEFA DE GOBIERNO", "JEFE DE",
               "JEFA DE", "TITULAR", "FISCAL", "PROCURADOR", "COORDINADOR",
               "COMISIONAD", "PRESIDENT", "VOCER", "CONSEJER", "OFICIAL MAYOR",
               "ENCARGAD")

# Entidades federativas, ordenadas para que el match más largo gane
# (p. ej. "BAJA CALIFORNIA SUR" antes que "BAJA CALIFORNIA").
ESTADOS = [
    "CIUDAD DE MEXICO", "ESTADO DE MEXICO", "BAJA CALIFORNIA SUR",
    "BAJA CALIFORNIA", "SAN LUIS POTOSI", "QUINTANA ROO", "NUEVO LEON",
    "AGUASCALIENTES", "CAMPECHE", "COAHUILA", "COLIMA", "CHIAPAS",
    "CHIHUAHUA", "DURANGO", "GUANAJUATO", "GUERRERO", "HIDALGO", "JALISCO",
    "MICHOACAN", "MORELOS", "NAYARIT", "OAXACA", "PUEBLA", "QUERETARO",
    "SINALOA", "SONORA", "TABASCO", "TAMAULIPAS", "TLAXCALA", "VERACRUZ",
    "YUCATAN", "ZACATECAS",
]


def normaliza_hablante(h: str) -> str:
    """Quita la anotación final entre paréntesis (p. ej. '(ENLACE
    VIDEOLLAMADA)') para que el mismo funcionario no se cuente dos veces.
    No toca paréntesis internos del cargo (p. ej. '(CONAGUA)')."""
    return TRAILING_PAREN.sub("", h).strip()


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _tiene_cargo(seg: str) -> bool:
    u = _sin_acentos(seg.upper())
    return any(k in u for k in CARGO_STEMS)


def _segmento_nombre(hablante: str) -> str:
    """Segmento que contiene el nombre, manejando 'CARGO, NOMBRE' y el formato
    invertido 'NOMBRE, CARGO' (incluso con cargos que llevan comas internas)."""
    segs = [s.strip() for s in hablante.split(",") if s.strip()]
    if len(segs) == 1:
        return segs[0]
    u0 = _sin_acentos(segs[0].upper())
    empieza_con_cargo = any(u0.startswith(k) for k in CARGO_STEMS)
    cand = segs[-1] if empieza_con_cargo else segs[0]
    # Si el candidato todavía contiene términos de cargo (línea mal partida),
    # usar el otro extremo si ése sí parece nombre limpio.
    if _tiene_cargo(cand):
        otro = segs[0] if cand is segs[-1] else segs[-1]
        if not _tiene_cargo(otro):
            cand = otro
    return cand


def _segmento_cargo(hablante: str) -> str:
    """El cargo = el hablante sin el segmento de nombre."""
    nombre = _segmento_nombre(hablante)
    segs = [s.strip() for s in hablante.split(",") if s.strip()]
    cargo = ", ".join(s for s in segs if s != nombre)
    return cargo or hablante


def clave_persona(hablante: str) -> str:
    """Clave de identidad por APELLIDOS (dos últimos tokens significativos),
    ignorando nombres de pila, segundos nombres, títulos y partículas. Así
    'CLARA BRUGADA MOLINA' = 'CLARA MARINA BRUGADA MOLINA' y
    'NOEMÍ JUÁREZ PÉREZ' = 'ANGÉLICA NOEMÍ JUÁREZ PÉREZ'."""
    nombre = _segmento_nombre(hablante)
    toks = [t for t in _sin_acentos(nombre.upper()).split()
            if t not in PARTICULAS and t not in HONORIFICOS]
    if not toks:
        return _sin_acentos(hablante.upper())
    return "|".join(toks[-2:])


def detecta_estado(hablante: str) -> str | None:
    """Identifica la entidad federativa en el cargo de un gobernador, para
    fusionar todas sus variantes (un gobernador por entidad)."""
    u = _sin_acentos(hablante.upper())
    # La Jefatura de Gobierno es única (CDMX), aunque omita "Ciudad de México"
    if "JEFE DE GOBIERNO" in u or "JEFA DE GOBIERNO" in u:
        return "CIUDAD DE MEXICO"
    for est in ESTADOS:
        if est in u:
            return est
    return None


def categoria_funcionario(nombre: str) -> str:
    u = _sin_acentos(nombre.upper())
    if "GOBERNADOR" in u or "JEFE DE GOBIERNO" in u or "JEFA DE GOBIERNO" in u:
        return "gobernadores"   # incluye Jefatura de Gobierno de la CDMX
    if "DIRECTOR" in u:
        return "directores"
    if "SECRETARI" in u:
        # 'Secretarios' = gabinete federal (incluye subsecretarios y titulares).
        # Se excluyen (→ otros): líderes sindicales, funcionarios extranjeros
        # y secretarías de gobiernos estatales.
        es_sindical = ("SINDICATO" in u or "CONFEDERACION" in u
                       or "SECRETARIO GENERAL" in u or "SECRETARIA GENERAL" in u)
        es_extranjero = "ESTADOS UNIDOS DE AMERICA" in u
        es_estatal = detecta_estado(nombre) is not None
        if es_sindical or es_extranjero or es_estatal:
            return "otros"
        return "secretarios"
    return "otros"


def clave_merge(hablante: str) -> str:
    """Clave para fusionar variantes del mismo funcionario. Gobernadores por
    entidad (robusto a erratas, apodos y formato); el resto por nombre."""
    if categoria_funcionario(hablante) == "gobernadores":
        est = detecta_estado(hablante)
        if est:
            return "GOB::" + est
    return clave_persona(hablante)
