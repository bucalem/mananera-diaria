"""
scraper_mananera.py
Fork de scraper_conferencias.py (analisis_discurso_presidencial).

Obtiene la versión estenográfica más reciente de la conferencia mañanera
(Presidencia de México) y la envía por correo vía Resend, con la transcripción
completa en el cuerpo y el .txt adjunto como respaldo.

gob.mx protege el sitio con un CryptoChallenge (Imperva), por lo que `requests`
no funciona: hace falta un navegador real. Playwright controla el Google Chrome
del sistema (channel="chrome") y sí pasa el challenge; si ese canal no está
disponible, cae al Chromium empaquetado de Playwright.

Variables de entorno:
    RESEND_API_KEY   API key de Resend (obligatoria para enviar)
    MAIL_TO          destinatarios separados por comas
    MAIL_FROM        remitente (default: onboarding@resend.dev)

Uso:
    python3 scraper_mananera.py            # flujo completo: scrape + correo
    python3 scraper_mananera.py --spike    # solo valida acceso a gob.mx
    python3 scraper_mananera.py --no-email # scrape y guarda, sin enviar
"""

import base64
import html
import json
import logging
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BASE_URL = "https://www.gob.mx"
ARCHIVO_URL = "https://www.gob.mx/presidencia/archivo/articulos?idiom=es&filter_origin=archive"

CORPUS_DIR = Path(__file__).parent / "corpus"
CORPUS_DIR.mkdir(exist_ok=True)

MAX_PAGINAS = 2         # solo las primeras páginas: buscamos la más reciente
PAUSA_S = 1.5           # pausa entre peticiones (segundos)
TIMEOUT_MS = 45000      # timeout de navegación (ms)

MAIL_FROM_DEFAULT = "onboarding@resend.dev"
RESEND_ENDPOINT = "https://api.resend.com/emails"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Utilidades (copiadas de scraper_conferencias.py)
# ---------------------------------------------------------------------------

def limpiar_parrafos(texto: str) -> str:
    """Colapsa las líneas en blanco: cada párrafo queda en una sola línea."""
    lineas = (ln.strip() for ln in texto.splitlines())
    return "\n".join(ln for ln in lineas if ln)


def fecha_de_url(url: str) -> str:
    m = re.search(r"del-(\d{1,2})-de-(\w+)-de-(\d{4})", url)
    if not m:
        return ""
    meses = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
    }
    dia, mes, anio = m.group(1), m.group(2).lower(), m.group(3)
    return f"{anio}-{meses.get(mes, '00')}-{dia.zfill(2)}"


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------

def lanzar_navegador(p):
    """Chrome del sistema si existe; si no, Chromium de Playwright."""
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
# Scraping
# ---------------------------------------------------------------------------

def buscar_mananera_reciente(page) -> dict | None:
    """Devuelve {url, titulo, fecha} de la conferencia de prensa más reciente."""
    for pag in range(1, MAX_PAGINAS + 1):
        url = (
            ARCHIVO_URL
            if pag == 1
            else f"{BASE_URL}/presidencia/es/archivo/articulos"
                 f"?filter_origin=archive&idiom=es&order=DESC&page={pag}"
        )
        log.info(f"Revisando archivo — página {pag}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            page.wait_for_selector("article", timeout=TIMEOUT_MS)
        except PWTimeout:
            log.warning(f"Timeout en página {pag} del archivo.")
            continue

        links = page.eval_on_selector_all(
            "article a[href*='/articulos/']",
            """els => els.map(a => ({
                href: a.getAttribute('href') || '',
                titulo: a.textContent.trim() || ''
            }))""",
        )

        # El archivo viene en orden DESC: el primer match es el más reciente.
        # El texto del link es "Continuar leyendo", así que se filtra por slug.
        for item in links:
            href, titulo = item["href"], item["titulo"]
            if "version-estenografica-conferencia-de-prensa" not in href:
                continue
            full = href if href.startswith("http") else BASE_URL + href
            fecha = fecha_de_url(full)
            if not fecha:
                continue
            return {"url": full, "titulo": titulo, "fecha": fecha}

        time.sleep(PAUSA_S)

    return None


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
            const fecha =
                document.querySelector("meta[name='date']")?.content ||
                document.querySelector("meta[property='article:published_time']")?.content?.slice(0,10) ||
                '';
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
            return { titulo, fecha, texto };
        }"""
    )
    datos["texto"] = limpiar_parrafos(datos["texto"])
    return datos


# ---------------------------------------------------------------------------
# Correo (Resend)
# ---------------------------------------------------------------------------

def construir_html(fecha: str, titulo: str, url: str, texto: str) -> str:
    parrafos = "\n".join(
        f"<p>{html.escape(ln)}</p>" for ln in texto.splitlines() if ln.strip()
    )
    return f"""\
<div style="font-family: Georgia, serif; max-width: 720px; margin: 0 auto; color: #1a1a1a;">
  <h1 style="font-size: 22px; line-height: 1.3;">{html.escape(titulo)}</h1>
  <p style="color: #666; font-size: 14px;">
    Fecha: {fecha} &nbsp;·&nbsp; <a href="{html.escape(url)}">Fuente (gob.mx)</a>
  </p>
  <hr style="border: none; border-top: 1px solid #ddd;">
  {parrafos}
</div>"""


def enviar_correo(fecha: str, titulo: str, url: str, texto: str, ruta_txt: Path) -> bool:
    api_key = os.environ.get("RESEND_API_KEY", "")
    mail_to = os.environ.get("MAIL_TO", "")
    mail_from = os.environ.get("MAIL_FROM", MAIL_FROM_DEFAULT)

    if not api_key or not mail_to:
        log.error("Faltan RESEND_API_KEY o MAIL_TO; no se puede enviar el correo.")
        return False

    destinatarios = [d.strip() for d in mail_to.split(",") if d.strip()]
    payload = {
        "from": f"Mañanera Diaria <{mail_from}>",
        "to": destinatarios,
        "subject": f"Mañanera {fecha} — {titulo[:120]}",
        "html": construir_html(fecha, titulo, url, texto),
        "attachments": [{
            "filename": ruta_txt.name,
            "content": base64.b64encode(ruta_txt.read_bytes()).decode("ascii"),
        }],
    }

    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            cuerpo = resp.read().decode("utf-8")
            log.info(f"Correo enviado a {destinatarios}: {cuerpo}")
            return True
    except urllib.error.HTTPError as e:
        log.error(f"Resend respondió {e.code}: {e.read().decode('utf-8', 'replace')}")
        return False
    except Exception as e:
        log.error(f"Error enviando correo: {e}")
        return False


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def spike(page):
    """Valida que el runner pase el challenge de Imperva: carga el archivo
    de Presidencia y reporta cuántos artículos ve. Guarda evidencia."""
    log.info("SPIKE: probando acceso a gob.mx…")
    try:
        page.goto(ARCHIVO_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        page.wait_for_selector("article", timeout=TIMEOUT_MS)
    except PWTimeout:
        page.screenshot(path="spike.png", full_page=True)
        Path("spike.html").write_text(page.content(), encoding="utf-8")
        log.error("SPIKE FALLÓ: no se cargaron artículos (posible bloqueo Imperva).")
        sys.exit(1)

    n = page.eval_on_selector_all("article", "els => els.length")
    page.screenshot(path="spike.png", full_page=True)
    Path("spike.html").write_text(page.content(), encoding="utf-8")
    log.info(f"SPIKE OK: {n} artículos visibles en el archivo de Presidencia.")
    sys.exit(0)


def main():
    modo_spike = "--spike" in sys.argv
    sin_correo = "--no-email" in sys.argv

    log.info("=" * 60)
    log.info(f"scraper_mananera — {datetime.now().isoformat()}")
    log.info("=" * 60)

    with sync_playwright() as p:
        browser = lanzar_navegador(p)
        context = nuevo_contexto(browser)
        page = context.new_page()

        try:
            if modo_spike:
                spike(page)

            meta = buscar_mananera_reciente(page)
            if not meta:
                log.error("No se encontró ninguna conferencia de prensa en el archivo.")
                sys.exit(1)

            fecha, titulo, url = meta["fecha"], meta["titulo"], meta["url"]
            log.info(f"Más reciente: {fecha} — …{url[-70:]}")

            ruta_txt = CORPUS_DIR / f"{fecha}.txt"
            if ruta_txt.exists():
                log.info(f"Sin novedad: {ruta_txt.name} ya existe. No se envía correo.")
                return

            time.sleep(PAUSA_S)
            datos = extraer_conferencia(page, url)
            if not datos or len(datos["texto"]) < 500:
                log.error("Texto insuficiente en la página de la conferencia.")
                sys.exit(1)

            titulo_final = datos["titulo"] or titulo
            ruta_txt.write_text(
                f"URL: {url}\nFecha: {fecha}\nTítulo: {titulo_final}\n\n{datos['texto']}",
                encoding="utf-8",
            )
            log.info(f"Guardada → {ruta_txt}")

            if sin_correo:
                log.info("Modo --no-email: no se envía correo.")
                return

            if not enviar_correo(fecha, titulo_final, url, datos["texto"], ruta_txt):
                # No dejar el .txt: así el siguiente run reintenta el envío
                ruta_txt.unlink(missing_ok=True)
                log.error("Envío fallido; se descarta el .txt para reintentar después.")
                sys.exit(1)

            log.info("✓ Completado: transcripción guardada y correo enviado.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
