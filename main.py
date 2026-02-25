"""Pipeline orquestador: Search → Score → Generate → Image → Publish."""

import logging
import sys
from datetime import datetime, timedelta, timezone

import config
import state
from search import search_all
from scorer import select_best
from content import generate_post
from image_gen import generate_cover_image
from wordpress import upload_media, create_draft
from source_fetch import enrich_article
from topics import TopicProfile, load_topics
from seo_rules import analyze_headline, analyze_truseo, build_slug

logger = logging.getLogger(__name__)


def _is_publish_due() -> bool:
    if config.PUBLISH_INTERVAL_DAYS == 0:
        return True

    last_published = state.get_last_published_at(statuses=("published_draft",))
    if last_published is None:
        return True

    next_allowed = last_published + timedelta(days=config.PUBLISH_INTERVAL_DAYS)
    now = datetime.now(timezone.utc)
    if now < next_allowed:
        wait = next_allowed - now
        remaining_days = round(wait.total_seconds() / 86400, 1)
        logger.info(
            (
                "Cadencia activa: último draft el %s UTC. "
                "Próxima publicación permitida el %s UTC (faltan ~%.1f días)."
            ),
            last_published.isoformat(timespec="seconds"),
            next_allowed.isoformat(timespec="seconds"),
            remaining_days,
        )
        return False
    return True


def _rotate_topics(topics: list[TopicProfile]) -> list[TopicProfile]:
    if len(topics) <= 1:
        return topics

    last_topic_id = state.get_last_published_topic_id(statuses=("published_draft",))
    if not last_topic_id:
        return topics

    idx = next((i for i, topic in enumerate(topics) if topic.topic_id == last_topic_id), -1)
    if idx == -1:
        return topics

    rotated = topics[idx + 1:] + topics[: idx + 1]
    logger.info(
        "Rotación de topics activa. Último publicado: %s | Orden actual: %s",
        last_topic_id,
        [t.topic_id for t in rotated],
    )
    return rotated


def run_topic_pipeline(topic: TopicProfile) -> bool:
    """Execute full pipeline for one topic. Returns True if a post was created."""
    logger.info("=== Topic: %s (%s) ===", topic.name, topic.topic_id)

    # 1. Search
    logger.info("=== Paso 1: Búsqueda de noticias ===")
    results = search_all(queries=topic.queries, topic_id=topic.topic_id)
    if not results:
        logger.info("No se encontraron noticias nuevas. Finalizando.")
        return False

    # 2. Score and select best
    logger.info("=== Paso 2: Evaluación de relevancia (%d artículos) ===", len(results))
    best = select_best(
        results,
        min_score=topic.min_score,
        topic_name=topic.name,
        topic_scoring_guidelines=topic.scoring_guidelines,
    )
    if best is None:
        logger.info("Ningún artículo alcanzó el umbral de calidad. Finalizando.")
        return False
    article, score = best
    logger.info("=== Paso 2.5: Enriquecimiento de fuente ===")
    article = enrich_article(article)

    # 3. Generate content
    logger.info("=== Paso 3: Generación de contenido ===")
    post = generate_post(
        article,
        topic_name=topic.name,
        topic_writing_guidelines=topic.writing_guidelines,
        template_name=topic.post_template,
    )
    if post is None:
        logger.error("No se pudo generar contenido. Finalizando.")
        state.mark_processed(
            article.url, title=article.title, score=score,
            status="gen_failed", topic_id=topic.topic_id,
        )
        return False
    if topic.categories:
        post.categories = topic.categories

    # 3.5 Local SEO gate (TruSEO-like + Headline) without AIOSEO API.
    truseo_score = None
    headline_score = None
    if config.LOCAL_SEO_RULES_ENABLED:
        truseo_report = analyze_truseo(
            html=post.body,
            seo_title=post.seo_title,
            meta_description=post.seo_description,
            slug=build_slug(post.seo_title or post.title),
            focus_keyphrase=post.focus_keyphrase,
            site_domain=config.WP_SITE_DOMAIN,
            strict_phrase=config.SEO_STRICT_PHRASE,
        )
        headline_report = analyze_headline(post.title, primary_keyword=post.focus_keyphrase)
        truseo_score = truseo_report["overall"].score
        headline_score = headline_report.score

        report_payload = {
            "truseo": {k: v.to_dict() for k, v in truseo_report.items()},
            "headline": headline_report.to_dict(),
            "thresholds": {
                "truseo_min_score": config.TRUSEO_MIN_SCORE,
                "headline_min_score": config.HEADLINE_MIN_SCORE,
            },
        }
        state.save_seo_report(
            topic_id=topic.topic_id,
            url=article.url,
            truseo_score=truseo_score,
            headline_score=headline_score,
            payload=report_payload,
        )

        logger.info(
            "SEO local [%s]: TruSEO-like=%d, Headline=%d",
            topic.topic_id,
            truseo_score,
            headline_score,
        )
        if truseo_score < config.TRUSEO_MIN_SCORE or headline_score < config.HEADLINE_MIN_SCORE:
            logger.warning(
                (
                    "SEO gate no pasó para '%s' (TruSEO-like=%d/%d, Headline=%d/%d). "
                    "Se deja fuera de publicación automática."
                ),
                post.title,
                truseo_score,
                config.TRUSEO_MIN_SCORE,
                headline_score,
                config.HEADLINE_MIN_SCORE,
            )
            state.mark_processed(
                article.url,
                title=post.title,
                score=score,
                status="seo_failed",
                topic_id=topic.topic_id,
            )
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
        if truseo_score is not None and headline_score is not None:
            logger.info("SEO local: TruSEO-like=%d | Headline=%d", truseo_score, headline_score)
        logger.info("Imagen: %s", image_path)
        state.mark_processed(
            article.url, title=post.title, score=score,
            status="dry_run", topic_id=topic.topic_id,
        )
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

    post_id = create_draft(post, media_id=media_id, author_name=topic.author_name)
    if post_id is None:
        logger.error("No se pudo crear el borrador en WordPress.")
        state.mark_processed(
            article.url, title=post.title, score=score,
            status="wp_failed", topic_id=topic.topic_id,
        )
        return False

    # 6. Record success
    state.mark_processed(
        article.url, title=post.title, score=score,
        wp_post_id=post_id, status="published_draft", topic_id=topic.topic_id,
    )
    logger.info("=== Pipeline completado: borrador #%d creado ===", post_id)
    return True


def run_pipeline() -> bool:
    """Execute topic-driven pipeline. Returns True if any post was created."""
    if not _is_publish_due():
        logger.info("No toca publicar en esta corrida.")
        return False

    topics = load_topics(config.TOPICS_FILE, only_ids=config.TOPIC_IDS)
    topics = _rotate_topics(topics)
    logger.info("Topics cargados: %s", [t.topic_id for t in topics])
    created = 0

    for topic in topics:
        if created >= config.TOPICS_MAX_POSTS_PER_RUN:
            logger.info(
                "Límite de publicaciones por corrida alcanzado (%d)",
                config.TOPICS_MAX_POSTS_PER_RUN,
            )
            break
        if run_topic_pipeline(topic):
            created += 1

    return created > 0


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
