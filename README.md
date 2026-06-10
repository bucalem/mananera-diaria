# Mañanera diaria por correo

Fork del scraper de `analisis_discurso_presidencial`: obtiene la versión
estenográfica más reciente de la conferencia mañanera (Presidencia de México)
y la envía por correo con la transcripción completa en el cuerpo y el `.txt`
adjunto como respaldo. Corre solo, de lunes a viernes a las 2 pm CDMX, en
GitHub Actions.

## Cómo funciona

1. Playwright carga el archivo de Presidencia en gob.mx (el sitio tiene un
   challenge de Imperva, por eso se usa un navegador real y no `requests`).
2. Busca en las primeras 2 páginas el link más reciente cuyo href contenga
   `version-estenografica` y cuyo título contenga "conferencia de prensa".
3. Si `corpus/{fecha}.txt` ya existe, termina sin enviar nada (también cubre
   fines de semana y feriados sin mañanera).
4. Si es nueva: extrae la transcripción, la guarda en `corpus/` (mismo formato
   que el corpus del proyecto original: `URL:/Fecha:/Título:` + texto) y envía
   el correo vía Resend. El workflow commitea el `.txt` al repo.
5. Si el envío falla, el `.txt` se descarta para que el siguiente run reintente.

## Configuración (Settings del repo)

| Tipo | Nombre | Valor |
|------|--------|-------|
| Secret | `RESEND_API_KEY` | API key de [resend.com](https://resend.com) |
| Variable | `MAIL_TO` | Destinatarios separados por comas |
| Variable | `MAIL_FROM` | Remitente (default: `onboarding@resend.dev`) |

> **Limitación de Resend sin dominio verificado:** con el remitente
> `onboarding@resend.dev` solo se puede enviar **a la dirección del dueño de la
> cuenta de Resend**. Para agregar más destinatarios hay que verificar un
> dominio propio en Resend y cambiar `MAIL_FROM`.

> **Nota sobre Gmail:** los correos de más de ~102 KB se recortan en la vista
> de Gmail ("Ver el mensaje completo"). El `.txt` adjunto garantiza que la
> transcripción íntegra siempre llegue.

## Uso local

```bash
pip3 install -r requirements.txt
python3 scraper_mananera.py --spike      # valida acceso a gob.mx
python3 scraper_mananera.py --no-email   # scrape sin enviar
RESEND_API_KEY=... MAIL_TO=tu@correo.com python3 scraper_mananera.py
```

## Validación en la nube

El workflow `Spike — acceso a gob.mx desde GitHub Actions` (manual) verifica
que el runner pase el challenge de Imperva antes de confiar en el cron diario.
Sube `spike.png` y `spike.html` como artifact de evidencia.
