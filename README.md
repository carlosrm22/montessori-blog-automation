# Montessori Blog Automation

Pipeline en Python para automatizar la curación y generación de borradores para un blog editorial por verticales temáticas.

El flujo completo hace lo siguiente:

1. Carga perfiles temáticos desde `topics.yml`.
2. Busca noticias recientes por tema (Brave Search API).
3. Evalúa relevancia con Gemini + heurísticas anti-evergreen.
4. Extrae texto real de la fuente para base factual.
5. Genera un artículo original en HTML.
6. Evalúa SEO local (TruSEO-like + Headline score) con reglas checklist sin usar API de AIOSEO.
7. Genera imagen de portada optimizada para WordPress.
8. Publica borrador en WordPress (AIOSEO API opcional y desactivada por defecto).
9. Guarda estado en SQLite por tema para no reprocesar URLs y reportes SEO por URL.

## Requisitos

- Python 3.10+
- Cuenta/API para:
  - Brave Search API
  - Gemini API (`google-genai`)
  - WordPress con Application Password

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
- `PUBLISH_INTERVAL_DAYS`: días mínimos entre publicaciones globales (default `7`, `0` = desactivar).
- `MIN_USABILITY_SCORE`: umbral mínimo para publicar.
- `MIN_BODY_WORDS`: mínimo de palabras requeridas para el body (default `600`).
- `DRY_RUN`: `1` para simular sin publicar; `0` para publicar borradores.
- `GEMINI_TEXT_MODEL`: modelo para scoring y generación de texto (default `gemini-2.5-flash`).
- `GEMINI_IMAGE_MODEL`: modelo para portada (default `gemini-2.5-flash-image`).
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
- `INTERNAL_LINKS`: fallback de enlaces internos reales (se usa solo si no hay enlaces internos válidos tras limpiar el contenido).
- `LINK_VALIDATION_ENABLED`: valida enlaces HTTP antes de publicar (`1` por defecto).
- `LINK_CHECK_TIMEOUT`: timeout (segundos) para validar cada URL (default `8`).
- `RECENT_POSTS_GALLERY_COUNT`: número de posts publicados reales a insertar en la galería final (default `4`, `0` = deshabilitar).
- `PREFERRED_EXTERNAL_LINK_EVERY`: inserta un enlace externo recomendado cada N publicaciones (default `3`, `0` = deshabilitar).
- `PREFERRED_EXTERNAL_LINKS`: lista de dominios externos recomendados separados por coma (rotación automática).
- `WP_IMAGE_WIDTH` / `WP_IMAGE_HEIGHT`: dimensiones objetivo de portada.
- `WP_IMAGE_QUALITY`: calidad JPEG inicial (1-100).
- `WP_IMAGE_MAX_KB`: peso objetivo máximo de imagen.
- `SOURCE_FETCH_ENABLED`: habilita extracción del texto real de la fuente antes de redactar.
- `SOURCE_FETCH_MAX_CHARS`: máximo de caracteres extraídos desde la nota origen.

## Topics.yml

El archivo [`topics.yml`](/home/carlos/montessori-blog-automation/topics.yml) define verticales con:

- `id`, `name`
- `author_name` (nombre del autor en WordPress para ese tema)
- `queries`
- `categories`
- `min_score`
- `post_template`
- `scoring_guidelines`
- `writing_guidelines`

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

## Programación automática (cron)

Recomendación: correr diario y dejar que el candado de cadencia (`PUBLISH_INTERVAL_DAYS`) decida si toca publicar.
Con `PUBLISH_INTERVAL_DAYS=7`, publicará aproximadamente cada semana sin intervención humana.

Ejemplo para correr todos los días a las 08:00:

```cron
0 8 * * * cd /home/carlos/montessori-blog-automation && /home/carlos/montessori-blog-automation/run.sh
```

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
├── image_gen.py     # Generación de portada con Gemini
├── wordpress.py     # Publicación de borradores vía WP REST API
├── notifier.py      # Envío de alertas al crear borradores
├── state.py         # Persistencia SQLite de URLs procesadas
├── config.py        # Carga/validación de configuración
├── templates/
│   └── post_prompt.txt
├── topics.yml        # Configuración editorial por vertical
├── data/
│   ├── blog_state.db
│   └── images/
└── logs/
```

## Salidas y estado

- Base de estado: `data/blog_state.db`
- Reportes SEO locales: tabla `seo_reports` en `data/blog_state.db`
- Imágenes: `data/images/`
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
- Se exige `title` corto (<=60), focus keyphrase en meta description, al menos un enlace interno y metadatos sociales OG/X.
- `seo_title`, `og_title` y `twitter_title` se normalizan al formato `Título | Sitio` (configurable).
- Antes de publicar, se limpian enlaces rotos/inválidos y solo se conservan URLs verificadas.
- La galería final de "Publicaciones Recientes" usa posts reales publicados en WordPress (no enlaces inventados).
- Cada cierto número de publicaciones se añade un recurso externo recomendado en rotación (`PREFERRED_EXTERNAL_LINKS`).
- Si la fuente no tiene URL pública válida (por ejemplo dominios `.local`), no se genera enlace roto en la atribución.
- El enfoque editorial es internacional por defecto; se añade contexto local solo cuando realmente aporta.
- El orden de publicación rota automáticamente por `topic_id` tomando como referencia el último borrador publicado.
- Cuando se crea un borrador, el sistema puede enviar una notificación con título, autor, puntajes SEO y enlace directo de edición.

## Licencia

Define aquí la licencia que quieras usar para el repositorio.
