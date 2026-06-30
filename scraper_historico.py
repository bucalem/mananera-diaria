"""
scraper_historico.py

Descarga TODAS las versiones estenográficas de la presidencia de Claudia
Sheinbaum desde el 1 de octubre de 2024 (toma de protesta incluida).
Pagina el archivo de Presidencia hasta encontrar artículos anteriores a esa
fecha, guarda cada transcripción en corpus/{fecha}.txt y omite los que ya
existen.

Uso:
    python3 scraper_historico.py              # descarga todo lo faltante
    python3 scraper_historico.py --dry-run    # lista URLs sin descargar
    python3 scraper_historico.py --max-pages 20  # límite de páginas (debug)
"""

import logging
import re
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_URL = "https://www.gob.mx"
ARCHIVO_URL = (
    "https://www.gob.mx/presidencia/archivo/articulos"
    "?idiom=es&filter_origin=archive"
)

FECHA_INICIO = date(2024, 10, 1)   # toma de protesta

CORPUS_DIR = Path(__file__).parent / "corpus"
CORPUS_DIR.mkdir(exist_ok=True)

PAUSA_S = 2.0
TIMEOUT_MS = 45_000
DEFAULT_MAX_PAGES = 200  # techo de seguridad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utilidades (mismas que en scraper_mananera.py)
# ---------------------------------------------------------------------------

def limpiar_parrafos(texto: str) -> str:
    lineas = (ln.strip() for ln in texto.splitlines())
    return "\n".join(ln for ln in lineas if ln)


def fecha_de_url(url: str) -> date | None:
    m = re.search(r"del-(\d{1,2})-de-(\w+)-de-(\d{4})", url)
    if not m:
        return None
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    dia, mes_str, anio = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    mes = meses.get(mes_str)
    if not mes:
        return None
    return date(anio, mes, dia)


def fecha_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------

def lanzar_navegador(p):
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
    ]
    try:
        return p.chromium.launch(channel="chrome", headless=True, args=args)
    except Exception as e:
        log.warning(f"Canal 'chrome' no disponible ({e}); usando Chromium empaquetado.")
        return p.chromium.launch(headless=True, args=args)


def nuevo_contexto(browser):
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="es-MX",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return context


# ---------------------------------------------------------------------------
# Recolección de URLs
# ---------------------------------------------------------------------------

def url_pagina(pag: int) -> str:
    if pag == 1:
        return ARCHIVO_URL
    return (
        f"{BASE_URL}/presidencia/es/archivo/articulos"
        f"?filter_origin=archive&idiom=es&order=DESC&page={pag}"
    )


def recolectar_urls(page, max_pages: int) -> list[dict]:
    """
    Retorna lista de {url, fecha, fecha_obj} ordenada de más reciente a más
    antigua, solo con artículos >= FECHA_INICIO.
    """
    resultados = []
    for pag in range(1, max_pages + 1):
        log.info(f"Paginando archivo — página {pag}")
        try:
            page.goto(url_pagina(pag), wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            page.wait_for_selector("article", timeout=TIMEOUT_MS)
        except PWTimeout:
            log.warning(f"Timeout en página {pag}; intentando continuar.")
            time.sleep(PAUSA_S * 2)
            continue

        links = page.eval_on_selector_all(
            "article a[href*='/articulos/']",
            "els => els.map(a => ({href: a.getAttribute('href') || ''}))",
        )

        encontro_algo = False
        supero_inicio = False

        for item in links:
            href = item["href"]
            # captura conferencias de prensa y toma de protesta
            if "version-estenografica" not in href:
                continue
            full = href if href.startswith("http") else BASE_URL + href
            fecha_obj = fecha_de_url(full)
            if not fecha_obj:
                continue
            if fecha_obj < FECHA_INICIO:
                supero_inicio = True
                continue
            encontro_algo = True
            resultados.append({
                "url": full,
                "fecha": fecha_str(fecha_obj),
                "fecha_obj": fecha_obj,
            })

        # Si en esta página ya encontramos artículos anteriores a FECHA_INICIO,
        # no tiene sentido seguir paginando (el archivo está en orden DESC).
        if supero_inicio:
            log.info(f"Encontrados artículos anteriores al {FECHA_INICIO}; detención.")
            break

        if not encontro_algo and pag > 1:
            log.info("Página sin resultados relevantes; fin del archivo.")
            break

        time.sleep(PAUSA_S)

    # Eliminar duplicados conservando orden
    vistos = set()
    unicos = []
    for r in resultados:
        if r["url"] not in vistos:
            vistos.add(r["url"])
            unicos.append(r)

    return sorted(unicos, key=lambda x: x["fecha_obj"])


# ---------------------------------------------------------------------------
# Extracción de transcripción
# ---------------------------------------------------------------------------

def extraer_conferencia(page, url: str) -> dict | None:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        page.wait_for_selector("h1, article, main", timeout=TIMEOUT_MS)
    except PWTimeout:
        log.warning(f"Timeout cargando {url}")
        return None

    datos = page.evaluate(
        """() => {
            const titulo = document.querySelector('h1')?.textContent?.trim() || '';
            const selectores = ['div.article-body','div.content','div.texto',
                                 'div.transcripcion','article','main'];
            let texto = '';
            for (const sel of selectores) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim().length > 300) {
                    texto = el.textContent.trim();
                    break;
                }
            }
            if (!texto) texto = document.body?.textContent?.trim() || '';
            texto = texto.replace(/[ \\t]{2,}/g, ' ');
            return { titulo, texto };
        }"""
    )
    datos["texto"] = limpiar_parrafos(datos["texto"])
    return datos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv
    max_pages = DEFAULT_MAX_PAGES
    for arg in sys.argv[1:]:
        if arg.startswith("--max-pages="):
            max_pages = int(arg.split("=")[1])

    log.info("=" * 60)
    log.info(f"scraper_historico — desde {FECHA_INICIO}")
    if dry_run:
        log.info("MODO DRY-RUN: no se descargará nada")
    log.info("=" * 60)

    with sync_playwright() as p:
        browser = lanzar_navegador(p)
        context = nuevo_contexto(browser)
        page = context.new_page()

        try:
            urls = recolectar_urls(page, max_pages)
            log.info(f"Total URLs encontradas: {len(urls)}")

            pendientes = [u for u in urls if not (CORPUS_DIR / f"{u['fecha']}.txt").exists()]
            ya_existen = len(urls) - len(pendientes)
            log.info(f"Ya en corpus: {ya_existen} | Por descargar: {len(pendientes)}")

            if dry_run:
                for u in pendientes:
                    log.info(f"  [pendiente] {u['fecha']}  {u['url']}")
                return

            ok, fallo = 0, 0
            for i, u in enumerate(pendientes, 1):
                log.info(f"[{i}/{len(pendientes)}] {u['fecha']} — {u['url'][-70:]}")
                datos = extraer_conferencia(page, u["url"])
                if not datos or len(datos["texto"]) < 500:
                    log.warning(f"  Texto insuficiente — omitido.")
                    fallo += 1
                    time.sleep(PAUSA_S)
                    continue

                ruta = CORPUS_DIR / f"{u['fecha']}.txt"
                ruta.write_text(
                    f"URL: {u['url']}\nFecha: {u['fecha']}\nTítulo: {datos['titulo']}\n\n{datos['texto']}",
                    encoding="utf-8",
                )
                log.info(f"  Guardada → {ruta.name}")
                ok += 1
                time.sleep(PAUSA_S)

            log.info("=" * 60)
            log.info(f"Completado: {ok} descargadas, {fallo} fallidas, {ya_existen} ya existían.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
