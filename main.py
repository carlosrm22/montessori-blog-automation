"""Pipeline orquestador: Search → Score → Generate → Image → Publish."""

import logging
import sys

import config
import state
from search import search_all
from scorer import select_best
from content import generate_post
from image_gen import generate_cover_image
from wordpress import upload_media, create_draft
from source_fetch import enrich_article

logger = logging.getLogger(__name__)


def run_pipeline() -> bool:
    """Execute the full pipeline. Returns True if a post was created."""
    # 1. Search
    logger.info("=== Paso 1: Búsqueda de noticias ===")
    results = search_all()
    if not results:
        logger.info("No se encontraron noticias nuevas. Finalizando.")
        return False

    # 2. Score and select best
    logger.info("=== Paso 2: Evaluación de relevancia (%d artículos) ===", len(results))
    best = select_best(results)
    if best is None:
        logger.info("Ningún artículo alcanzó el umbral de calidad. Finalizando.")
        return False
    article, score = best
    logger.info("=== Paso 2.5: Enriquecimiento de fuente ===")
    article = enrich_article(article)

    # 3. Generate content
    logger.info("=== Paso 3: Generación de contenido ===")
    post = generate_post(article)
    if post is None:
        logger.error("No se pudo generar contenido. Finalizando.")
        state.mark_processed(article.url, title=article.title, score=score, status="gen_failed")
        return False

    # 4. Generate cover image
    logger.info("=== Paso 4: Generación de imagen de portada ===")
    image_path = generate_cover_image(post.image_prompt)

    # 5. Publish to WordPress
    if config.DRY_RUN:
        logger.info("=== DRY_RUN: Omitiendo publicación en WordPress ===")
        logger.info("Título: %s", post.title)
        logger.info("Excerpt: %s", post.excerpt)
        logger.info("Categorías: %s", post.categories)
        logger.info("Tags: %s", post.tags)
        logger.info("Imagen: %s", image_path)
        state.mark_processed(article.url, title=post.title, score=score, status="dry_run")
        return True

    logger.info("=== Paso 5: Publicación en WordPress (borrador) ===")
    media_id = None
    if image_path:
        media_id = upload_media(
            image_path,
            title=post.title,
            alt_text=post.image_alt_text,
            caption=post.excerpt or post.title,
            description=post.seo_description or post.excerpt,
        )
        if media_id is None:
            logger.warning("No se pudo subir la imagen, continuando sin imagen destacada")

    post_id = create_draft(post, media_id=media_id)
    if post_id is None:
        logger.error("No se pudo crear el borrador en WordPress.")
        state.mark_processed(article.url, title=post.title, score=score, status="wp_failed")
        return False

    # 6. Record success
    state.mark_processed(
        article.url, title=post.title, score=score,
        wp_post_id=post_id, status="published_draft",
    )
    logger.info("=== Pipeline completado: borrador #%d creado ===", post_id)
    return True


def main() -> None:
    config.setup_logging()
    config.validate()
    logger.info("Iniciando pipeline Montessori Blog Automation (DRY_RUN=%s)", config.DRY_RUN)

    try:
        success = run_pipeline()
        if success:
            logger.info("Pipeline finalizado exitosamente.")
        else:
            logger.info("Pipeline finalizado sin crear post.")
    except Exception:
        logger.exception("Error fatal en el pipeline")
        sys.exit(1)


if __name__ == "__main__":
    main()
