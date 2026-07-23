# Montessori Blog Automation

Pipeline en Python para automatizar la curación y generación de borradores para un blog editorial por verticales temáticas.

El flujo completo hace lo siguiente:

1. Carga perfiles temáticos desde `topics.yml`.
2. Busca noticias recientes por tema (Brave Search API).
3. Evalúa relevancia con Gemini + heurísticas anti-evergreen.
4. Extrae texto real de la fuente para base factual.
5. Genera un artículo original en HTML.
6. Evalúa SEO local (TruSEO-like + Headline score) con reglas checklist sin usar API de AIOSEO.
7. Guarda el artículo completo en una cola persistente y envía por Telegram el prompt exacto de portada.
8. Espera una imagen creada manualmente en ChatGPT; no crea todavía ningún borrador en WordPress.
9. Valida, recorta y optimiza la portada a `1200x630`, y solo entonces crea el borrador con imagen destacada.
10. Guarda estado en SQLite por tema para no reprocesar URLs y reportes SEO por URL.

## Requisitos

- Python 3.10+
- Cuenta/API para:
  - Brave Search API
  - Gemini API (`google-genai`) para análisis y redacción
  - WordPress con Application Password
- ChatGPT con generación de imágenes para crear las portadas del flujo manual.

## Instalación

```bash
git clone https://github.com/carlosrm22/montessori-blog-automation.git
cd montessori-blog-automation

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración

1. Copia variables de entorno:

```bash
cp .env.example .env
```

2. Edita `.env` y completa credenciales.

Variables principales:

- `GEMINI_API_KEY`: API key de Gemini.
- `SEARCH_PROVIDER`: proveedor de búsqueda (`brave` por defecto, `google_cse` opcional).
- `BRAVE_SEARCH_API_KEY`: API key de Brave Search.
- `BRAVE_SEARCH_COUNT`: cantidad de resultados por query en Brave (default `20`).
- `BRAVE_SEARCH_COUNTRY`: país para Brave (vacío = sin restricción geográfica).
- `BRAVE_SEARCH_LANG`: idioma para Brave (vacío = cualquier idioma).
- `BRAVE_SEARCH_FRESHNESS`: filtro temporal Brave (`pd`, `pw`, `pm`, `py`; default `pw`).
- `EXCLUDED_DOMAINS`: dominios a excluir de resultados (default `montessorimexico.org`).
- `BLOCKED_SOURCE_TERMS`: términos para descartar fuentes no deseadas (default incluye AMI/AMI México y variantes).
- `BLOCKED_MENTION_TERMS`: términos prohibidos dentro del contenido generado (default incluye AMI/AMI México y variantes).
- `GOOGLE_CSE_KEY` y `GOOGLE_CSE_CX`: opcionales, solo si usas `SEARCH_PROVIDER=google_cse`.
- `WP_SITE_URL`: URL base de WordPress (sin slash final).
- `WP_USERNAME`: usuario de WordPress.
- `WP_APP_PASSWORD`: Application Password de WordPress.
- `SEARCH_QUERIES`: fallback de consultas separadas por coma (solo si falta `topics.yml`).
- `TOPIC_IDS`: lista separada por coma para correr solo ciertos temas (ej. `montessori_core,constructivismo`).
- `TOPICS_MAX_POSTS_PER_RUN`: máximo de borradores por corrida.
- `MIN_DRAFT_BUFFER`: mínimo de borradores activos en WordPress que se intentan mantener; si hay menos, el pipeline puede publicar aunque no se haya cumplido la cadencia.
- `PUBLISH_INTERVAL_DAYS`: días mínimos entre publicaciones globales cuando el colchón de borradores está sano (default `7`, `0` = desactivar).
- `MIN_USABILITY_SCORE`: umbral mínimo para publicar.
- `MIN_BODY_WORDS`: mínimo de palabras requeridas para el body (default `600`).
- `DRY_RUN`: `1` para simular sin publicar; `0` para publicar borradores.
- `GEMINI_TEXT_MODEL`: modelo legacy usado como fallback para scoring/contenido si no defines los modelos específicos (default `gemini-3.5-flash`).
- `GEMINI_SCORER_MODEL`: modelo para scoring de relevancia (default `gemini-3.5-flash-lite`, o `GEMINI_TEXT_MODEL` si está definido).
- `GEMINI_CONTENT_MODEL`: modelo para generación de artículos (default `gemini-3.5-flash`, o `GEMINI_TEXT_MODEL` si está definido).
- `SCORER_MIN_INTERVAL_SECONDS`: separación mínima entre evaluaciones Gemini; `4.1` respeta el límite gratuito de 15 solicitudes por minuto (`0` desactiva el ritmo).
- `GEMINI_IMAGE_MODEL`: modelo para portada (default `gemini-2.5-flash-image`).
- `IMAGE_WORKFLOW`: `manual` (default) guarda un paquete y espera una portada creada en ChatGPT; `gemini` conserva el generador de imágenes por API como alternativa.
- `MANUAL_IMAGE_MAX_MB`: tamaño máximo admitido para la imagen manual antes de procesarla (default `20`).
- `REQUIRE_FEATURED_IMAGE`: `1` bloquea la creación del borrador si falta la portada o WordPress no acepta su subida (default y recomendado); `0` permite borradores sin imagen destacada en el flujo `gemini`.
- `AIOSEO_SYNC`: `1` para sincronizar title/description/OG/Twitter en AIOSEO (opcional, default `0`).
- `LOCAL_SEO_RULES_ENABLED`: habilita evaluación SEO local (`1` por defecto).
- `TRUSEO_MIN_SCORE`: mínimo TruSEO-like para publicar automáticamente (default `70`).
- `HEADLINE_MIN_SCORE`: mínimo Headline score para publicar automáticamente (default `65`).
- `SEO_STRICT_PHRASE`: `1` para coincidencia estricta de focus keyphrase; `0` modo más permisivo.
- `NOTIFICATIONS_ENABLED`: activa avisos al crear borradores (default `1`).
- `NOTIFY_WEBHOOK_URL`: webhook para recibir alertas (Slack/Discord/Make/n8n, opcional).
- `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`: canal alterno de alertas por Telegram.
- `POST_TITLE_MAX_LEN`: máximo de caracteres para el título del post (default `60`).
- `SEO_TITLE_MAX_LEN`: máximo de caracteres para SEO title (default `60`).
- `SEO_DESCRIPTION_MAX_LEN`: máximo de caracteres para meta description (default `155`).
- `SOCIAL_TITLE_MAX_LEN`: máximo de caracteres para títulos sociales OG/Twitter (default `60`).
- `SOCIAL_DESCRIPTION_MAX_LEN`: máximo de caracteres para descripciones sociales OG/Twitter (default `155`).
- `FOCUS_KEYPHRASE_MAX_WORDS`: máximo de palabras para la keyphrase principal (default `5`).
- `EXCERPT_MAX_LEN`: máximo de caracteres para excerpt (default `160`).
- `MAX_TAGS`: máximo de tags por post (default `10`).
- `SITE_TITLE`: nombre del sitio para títulos SEO/social (ej. `Asociación Montessori de México`).
- `TITLE_SEPARATOR`: separador entre título de entrada y nombre del sitio (ej. `|`).
- `BRAND_KIT`: kit visual global para portadas (`ammac` o `kalpilli`).
- `BRAND_KITS_FILE`: ruta al archivo YAML de brand kits (default `brand_kits.yml`).
- `BRAND_LOGO_ENABLED`: habilita superposición del logo del brand kit en la portada (`0` por defecto, recomendado activar primero en pruebas).
- `INTERNAL_LINKS`: fallback de enlaces internos reales (se usa solo si no hay enlaces internos válidos tras limpiar el contenido).
- `LINK_VALIDATION_ENABLED`: valida enlaces HTTP antes de publicar (`1` por defecto).
- `LINK_CHECK_TIMEOUT`: timeout (segundos) para validar cada URL (default `8`).
- `RECENT_POSTS_GALLERY_COUNT`: número de posts publicados reales a insertar en la galería final (default `4`, `0` = deshabilitar).
- `QUALITY_RECENT_POSTS_COUNT`: títulos recientes de WordPress comparados por el gate de novedad (default `30`).
- `TITLE_SIMILARITY_MAX`: similitud máxima aceptada antes de rechazar el borrador (default `0.82`).
- `CONVERSION_CTA_ENABLED`: `0` mantiene clasificación y logs activos sin insertar CTA controlados; la higiene comercial todavía elimina destinos redactados por el modelo. Cambia a `1` solo después de comprobar que todas las URLs de programas responden con HTTP 200.
- `CERTIFICATION_SITE_URL`: origen HTTPS canónico para las rutas controladas de programas.
- `WHATSAPP_PHONE`: solo los dígitos del WhatsApp institucional, sin `+` ni espacios.
- `PREFERRED_EXTERNAL_LINK_EVERY`: inserta un enlace externo recomendado cada N publicaciones (default `3`, `0` = deshabilitar).
- `PREFERRED_EXTERNAL_LINKS`: lista de dominios externos recomendados separados por coma (rotación automática).
- `WP_IMAGE_WIDTH` / `WP_IMAGE_HEIGHT`: dimensiones objetivo de portada.
- `WP_IMAGE_QUALITY`: calidad JPEG inicial (1-100).
- `WP_IMAGE_MAX_KB`: peso objetivo máximo de imagen.
- `SOURCE_FETCH_ENABLED`: habilita extracción del texto real de la fuente antes de redactar.
- `SOURCE_FETCH_MAX_CHARS`: máximo de caracteres extraídos desde la nota origen.

### Enrutamiento de conversión

El clasificador solo acepta los siguientes intents. Cualquier otro valor, o relevancia `low`, se normaliza a `editorial / low` sin destino comercial.

| Intent | Ruta controlada |
| --- | --- |
| `nido` | `/diplomados/nido-comunidad-infantil/` |
| `casa` | `/diplomados/casa-de-ninos/` |
| `taller` | `/diplomados/taller-i-ii/` |
| `cosmica` | `/diplomados/educacion-cosmica/` |
| `neuro` | `/diplomados/neuroeducacion/` |
| `general_training` | `/diplomados/` |

Con relevancia `medium` se genera un enlace contextual controlado. Con `high`, también se genera el bloque final y el enlace institucional de WhatsApp. La inserción solo ocurre con `CONVERSION_CTA_ENABLED=1`; antes de aplicar el embudo, ambos pipelines eliminan enlaces comerciales redactados por el modelo.

## Topics.yml

El archivo [`topics.yml`](/home/carlos/montessori-blog-automation/topics.yml) define verticales con:

- `id`, `name`
- `author_name` (nombre del autor en WordPress para ese tema)
- `brand_kit` (opcional por tema; fallback a `BRAND_KIT`)
- `queries`
- `categories`
- `min_score`
- `post_template`
- `scoring_guidelines`
- `writing_guidelines`

El archivo [`brand_kits.yml`](/home/carlos/montessori-blog-automation/brand_kits.yml) define estilo visual por marca:

- `prompt_prefix`
- `human_presence` (`high`, `medium`, `low`) para controlar si la portada prioriza personas, manos/figuras parciales o solo materiales/ambiente
- `palette`
- `negative`
- `postprocess` (tinte, contraste, saturación)
- `logo` (ruta, posición, escala, opacidad y margen)

Valores de `human_presence`:

- `high`: personas visibles como parte de la escena, manteniendo niñas y niños no identificables.
- `medium`: manos, figuras parciales, vista lateral/de espaldas y Guía acompañando sin rostros centrales.
- `low`: materiales Montessori, detalles del ambiente preparado y presencia humana mínima.

## Ejecución

Con wrapper:

```bash
./run.sh
```

Directo con Python:

```bash
source .venv/bin/activate
python main.py
```

### Portadas manuales con ChatGPT

Con `IMAGE_WORKFLOW=manual`, una corrida válida genera como máximo un paquete pendiente y **no crea un borrador de WordPress**. Telegram entrega el ID único, título, texto alternativo, prompt exacto, ruta esperada para la imagen y comando de reanudación.

Procedimiento:

1. Copia en ChatGPT el prompt recibido por Telegram y genera la portada.
2. Descarga la imagen como PNG, JPG/JPEG o WEBP. Debe medir al menos `600x315` px.
3. Guárdala con el ID indicado, por ejemplo:

```text
/home/carlos/montessori-blog-automation/data/manual_image_queue/inbox/img-20260722-120000-1234abcd.png
```

4. Ejecuta el comando incluido en Telegram:

```bash
/home/carlos/montessori-blog-automation/process_manual_cover.sh img-20260722-120000-1234abcd
```

También puedes conservar la imagen en cualquier ubicación y pasar su ruta explícitamente:

```bash
./process_manual_cover.sh img-20260722-120000-1234abcd /ruta/a/portada.webp
```

El procesador valida el archivo, elimina metadatos, normaliza orientación, recorta sin deformar, aplica el brand kit, optimiza a JPEG y sube la portada. El borrador se crea únicamente después de que WordPress confirma la imagen destacada.

Si se interrumpe una subida o la creación del post, vuelve a ejecutar el mismo comando. El trabajo conserva su etapa, reutiliza la imagen o `media_id` existente y busca un borrador coincidente antes de crear otro. Mientras haya un paquete pendiente, ambos generadores bloquean paquetes nuevos.

Rutas operativas:

- Pendientes: `data/manual_image_queue/jobs/`
- Entrada de imágenes: `data/manual_image_queue/inbox/`
- Completados: `data/manual_image_queue/completed/`

No edites `job.json` manualmente. Un contrato dañado se bloquea deliberadamente para evitar publicaciones incompletas.

Ver reportes SEO locales guardados:

```bash
python report_seo.py --limit 20
python report_seo.py --only-failed
python report_seo.py --topic-id educacion_humanista
```

## Modo seguro (recomendado al inicio)

Ejecuta primero en simulación para validar prompts y scoring:

```bash
DRY_RUN=1 ./run.sh
```

En este modo no publica en WordPress, pero sí ejecuta búsqueda, evaluación, generación y registro de estado.

## Programación automática (systemd)

Recomendación: correr diario y combinar cadencia con un colchón mínimo de borradores.
Con `MIN_DRAFT_BUFFER=2` y `PUBLISH_INTERVAL_DAYS=1`, el sistema intentará mantener al menos dos borradores activos y nunca publicará más de una vez al día salvo que ajustes también el límite por corrida.

El repositorio incluye units listos para `systemd --user` en `systemd/montessori-blog.service` y `systemd/montessori-blog.timer`.

Instalación recomendada:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/montessori-blog.service ~/.config/systemd/user/
cp systemd/montessori-blog.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now montessori-blog.timer
loginctl enable-linger "$USER"
```

Verificación:

```bash
systemctl --user status montessori-blog.timer
systemctl --user list-timers --all | grep montessori-blog
journalctl --user -u montessori-blog.service -n 50 --no-pager
```

La programación queda diaria a las `08:00` y `Persistent=true` hace que, si la máquina estaba apagada o hibernada a esa hora, la corrida pendiente se ejecute al reanudar o iniciar sesión.

`cron` puede seguir funcionando como alternativa, pero no recupera ejecuciones perdidas cuando el equipo está dormido.

## Estructura del proyecto

```text
.
├── main.py          # Orquestador del pipeline
├── search.py        # Búsqueda de noticias (Brave / Google CSE)
├── topics.py        # Carga y validación de perfiles temáticos
├── scorer.py        # Scoring de relevancia con Gemini
├── seo_rules.py     # TruSEO-like + Headline scoring local
├── content.py       # Generación de artículo en HTML
├── source_fetch.py  # Fetch + extracción de contenido de la fuente
├── image_gen.py     # Generación o preparación segura de portadas
├── manual_image_queue.py # Cola persistente de una portada manual
├── resume_manual_image.py # Reanuda el paquete y crea el borrador
├── process_manual_cover.sh # Comando operativo para procesar la imagen
├── branding.py      # Brand kits (prompt wrapper + postproceso visual)
├── assets/logos/    # Logos para overlay opcional en portadas
├── wordpress.py     # Publicación de borradores vía WP REST API
├── notifier.py      # Envío de alertas al crear borradores
├── state.py         # Persistencia SQLite de URLs procesadas
├── config.py        # Carga/validación de configuración
├── templates/
│   └── post_prompt.txt
├── systemd/
│   ├── montessori-blog.service
│   └── montessori-blog.timer
├── topics.yml        # Configuración editorial por vertical
├── brand_kits.yml    # Configuración visual de marca para portadas
├── data/
│   ├── blog_state.db
│   ├── images/
│   └── manual_image_queue/
└── logs/
```

## Salidas y estado

- Base de estado: `data/blog_state.db`
- Reportes SEO locales: tabla `seo_reports` en `data/blog_state.db`
- Imágenes: `data/images/`
- Cola manual de portadas: `data/manual_image_queue/`
- Logs rotativos: `logs/automation.log`

## Notas operativas

- El proyecto evita duplicados al guardar URLs ya procesadas.
- Si falla generación o publicación, registra estado (`gen_failed`, `wp_failed`, etc.).
- Categorías y tags en WordPress se resuelven/crean automáticamente.
- Los resultados de `EXCLUDED_DOMAINS` se filtran para evitar auto-referencias del propio sitio.
- `BLOCKED_SOURCE_TERMS` descarta fuentes AMI/AMI México (u otras que definas).
- `BLOCKED_MENTION_TERMS` evita que el texto final mencione AMI/AMI México.
- Se actualizan `alt_text`, `caption` y `description` de la imagen destacada para accesibilidad.
- El scoring penaliza páginas evergreen (home/about/wiki) y prioriza contenido más noticioso/reciente.
- El SEO gate local calcula `TruSEO-like` y `Headline score`; si no pasan umbral se marca `seo_failed` y no publica.
- El gate de novedad compara el título editorial con publicaciones recientes antes de generar la portada o escribir en WordPress.
- Se exige `title` corto (<=60), focus keyphrase en meta description, al menos un enlace interno y metadatos sociales OG/X.
- `seo_title`, `og_title` y `twitter_title` se normalizan al formato `Título | Sitio` (configurable).
- La portada manual aplica `brand kit` (prompt + color grading) para consistencia visual por marca.
- Opcionalmente puede superponer un logo de marca (overlay sutil) cuando `BRAND_LOGO_ENABLED=1`.
- Antes de publicar, se limpian enlaces rotos/inválidos y solo se conservan URLs verificadas.
- La galería final de "Publicaciones Recientes" usa posts reales publicados en WordPress (no enlaces inventados).
- Cada cierto número de publicaciones se añade un recurso externo recomendado en rotación (`PREFERRED_EXTERNAL_LINKS`).
- Si la fuente no tiene URL pública válida (por ejemplo dominios `.local`), no se genera enlace roto en la atribución.
- El enfoque editorial es internacional por defecto; se añade contexto local solo cuando realmente aporta.
- El orden de publicación rota automáticamente por `topic_id` tomando como referencia el último borrador publicado.
- Telegram avisa primero cuando falta la portada y vuelve a notificar cuando el borrador completo ya existe.
- Los dos pipelines crean únicamente posts con estado `draft`; la creación de borradores no publica el post ni llama a IndexNow.

## Licencia

Define aquí la licencia que quieras usar para el repositorio.
