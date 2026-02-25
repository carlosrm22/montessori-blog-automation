# Montessori Blog Automation

Pipeline en Python para automatizar la curación y generación de borradores para un blog Montessori en México.

El flujo completo hace lo siguiente:

1. Busca noticias recientes con Google Custom Search.
2. Evalúa relevancia con Gemini.
3. Genera un artículo original en HTML.
4. Genera imagen de portada.
5. Publica un borrador en WordPress (o simula en modo `DRY_RUN`).
6. Guarda estado en SQLite para no reprocesar URLs.

## Requisitos

- Python 3.10+
- Cuenta/API para:
  - Google Custom Search JSON API
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
- `GOOGLE_CSE_KEY`: API key de Google Custom Search.
- `GOOGLE_CSE_CX`: ID del buscador personalizado.
- `WP_SITE_URL`: URL base de WordPress (sin slash final).
- `WP_USERNAME`: usuario de WordPress.
- `WP_APP_PASSWORD`: Application Password de WordPress.
- `SEARCH_QUERIES`: consultas separadas por coma.
- `MIN_USABILITY_SCORE`: umbral mínimo para publicar.
- `DRY_RUN`: `1` para simular sin publicar; `0` para publicar borradores.
- `GEMINI_TEXT_MODEL`: modelo para scoring y generación de texto (default `gemini-2.5-flash`).
- `GEMINI_IMAGE_MODEL`: modelo para portada (default `gemini-2.5-flash-image`).

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

## Modo seguro (recomendado al inicio)

Ejecuta primero en simulación para validar prompts y scoring:

```bash
DRY_RUN=1 ./run.sh
```

En este modo no publica en WordPress, pero sí ejecuta búsqueda, evaluación, generación y registro de estado.

## Programación automática (cron)

Ejemplo para correr cada día a las 08:00:

```cron
0 8 * * * cd /home/carlos/montessori-blog-automation && /home/carlos/montessori-blog-automation/run.sh
```

## Estructura del proyecto

```text
.
├── main.py          # Orquestador del pipeline
├── search.py        # Búsqueda de noticias (Google CSE)
├── scorer.py        # Scoring de relevancia con Gemini
├── content.py       # Generación de artículo en HTML
├── image_gen.py     # Generación de portada con Gemini
├── wordpress.py     # Publicación de borradores vía WP REST API
├── state.py         # Persistencia SQLite de URLs procesadas
├── config.py        # Carga/validación de configuración
├── templates/
│   └── post_prompt.txt
├── data/
│   ├── blog_state.db
│   └── images/
└── logs/
```

## Salidas y estado

- Base de estado: `data/blog_state.db`
- Imágenes: `data/images/`
- Logs rotativos: `logs/automation.log`

## Notas operativas

- El proyecto evita duplicados al guardar URLs ya procesadas.
- Si falla generación o publicación, registra estado (`gen_failed`, `wp_failed`, etc.).
- Categorías y tags en WordPress se resuelven/crean automáticamente.

## Licencia

Define aquí la licencia que quieras usar para el repositorio.
