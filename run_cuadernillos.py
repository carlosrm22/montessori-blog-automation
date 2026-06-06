"""Runner de la fuente "cuadernillos": una publicación por cada cuadernillo del
Diplomado AMMAC, firmada por el autor de su materia, sin mencionar el cuadernillo.

Independiente del pipeline de noticias:
- ignora MAX_DRAFT_BACKLOG (tiene su propio tope por corrida, CUADERNILLOS_MAX_PER_RUN)
- usa status "cuadernillo_draft" para NO afectar la cadencia/rotación de noticias
- es reanudable: el state evita repetir cuadernillos ya generados

Uso:
  python run_cuadernillos.py --limit 1 --dry-run      # prueba, no publica ni marca
  python run_cuadernillos.py                          # lote (default config)
  python run_cuadernillos.py --limit 0                # todos los pendientes
  python run_cuadernillos.py --materia campanas       # solo una materia
  python run_cuadernillos.py --author-only Carlos     # solo materias de un autor
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import config
import cuadernillo_source as cs
import state
from content import generate_post
from image_gen import generate_cover_image
from link_optimizer import sanitize_and_enrich_body
from notifier import notify_draft_created
from search import SearchResult
from seo_rules import analyze_headline, analyze_truseo, build_slug
from wordpress import create_draft, list_recent_published_posts, upload_media

logger = logging.getLogger(__name__)

TEMPLATE = "cuadernillo_prompt.txt"
STATUS_DRAFT = "cuadernillo_draft"
STATUS_FAILED = "cuad_gen_failed"


def _process_one(item: cs.Cuadernillo, dry_run: bool) -> bool:
    logger.info(
        "=== Cuadernillo %s/s%d :: %s (autor: %s) ===",
        item.materia_id, item.session_n, item.topic_label, item.author_name,
    )

    article = SearchResult(
        title=item.topic_label,
        url=item.pseudo_url,
        snippet="",
        source_text=item.source_text,
    )

    writing_guidelines = (
        f"Tema del área Montessori: {item.materia_name}. Desarrolla el concepto con "
        "profundidad pedagógica y aplicabilidad real, como artículo de divulgación."
    )

    post = generate_post(
        article,
        topic_name=item.topic_label,
        topic_writing_guidelines=writing_guidelines,
        template_name=TEMPLATE,
        author_name=item.author_name,
        tone_file=item.tone_file,
    )
    if post is None:
        logger.error("No se pudo generar contenido para %s.", item.pseudo_url)
        if not dry_run:
            state.mark_processed(
                item.pseudo_url, title=item.topic_label,
                status=STATUS_FAILED, topic_id=item.topic_id,
            )
        return False

    post.categories = item.categories or post.categories

    # Higiene de enlaces (sin source_url; añade internos a partir de posts recientes)
    recent_posts: list[dict] = []
    gallery_n = getattr(config, "RECENT_POSTS_GALLERY_COUNT", 0)
    if gallery_n and not dry_run:
        recent_posts = list_recent_published_posts(limit=gallery_n)
    post.body, _ = sanitize_and_enrich_body(
        html=post.body, source_url="", recent_posts=recent_posts,
    )

    # SEO local: se calcula y registra (NO se usa como filtro: queremos cubrir todo).
    truseo_score = headline_score = None
    if config.LOCAL_SEO_RULES_ENABLED:
        truseo = analyze_truseo(
            html=post.body, post_title=post.title, seo_title=post.seo_title,
            meta_description=post.seo_description,
            slug=build_slug(post.seo_title or post.title),
            focus_keyphrase=post.focus_keyphrase, site_domain=config.WP_SITE_DOMAIN,
            og_title=post.og_title, og_description=post.og_description,
            twitter_title=post.twitter_title, twitter_description=post.twitter_description,
            social_image_source=post.social_image_source,
            post_title_max_len=config.POST_TITLE_MAX_LEN,
            strict_phrase=config.SEO_STRICT_PHRASE,
        )
        headline = analyze_headline(post.title, primary_keyword=post.focus_keyphrase)
        truseo_score, headline_score = truseo["overall"].score, headline.score
        logger.info("SEO local: TruSEO-like=%d | Headline=%d", truseo_score, headline_score)
        if not dry_run:
            state.save_seo_report(
                topic_id=item.topic_id, url=item.pseudo_url,
                truseo_score=truseo_score, headline_score=headline_score,
                payload={"truseo": {k: v.to_dict() for k, v in truseo.items()},
                         "headline": headline.to_dict()},
            )

    image_path = generate_cover_image(post.image_prompt, brand_id=item.brand_kit)

    if dry_run:
        logger.info("=== DRY_RUN: no se publica ni se marca ===")
        logger.info("Título: %s", post.title)
        logger.info("Categorías: %s | Imagen: %s", post.categories, image_path)
        return True

    media_id = None
    if image_path:
        media_id = upload_media(
            image_path, title=post.title, alt_text=post.image_alt_text,
            caption=post.excerpt or post.title,
            description=post.seo_description or post.excerpt,
        )

    post_id = create_draft(post, media_id=media_id, author_name=item.author_name)
    if post_id is None:
        logger.error("No se pudo crear el borrador para %s.", item.pseudo_url)
        state.mark_processed(
            item.pseudo_url, title=post.title,
            status=STATUS_FAILED, topic_id=item.topic_id,
        )
        return False

    state.mark_processed(
        item.pseudo_url, title=post.title, wp_post_id=post_id,
        status=STATUS_DRAFT, topic_id=item.topic_id,
    )
    notify_draft_created(
        post_id=post_id, title=post.title, topic_name=item.materia_name,
        author_name=item.author_name,
        edit_url=f"{config.WP_SITE_URL}/wp-admin/post.php?post={post_id}&action=edit",
        truseo_score=truseo_score, headline_score=headline_score,
    )
    logger.info("=== Cuadernillo publicado como borrador #%d ===", post_id)
    return True


def run(limit: int, materia: str = "", author_only: str = "", dry_run: bool = False) -> int:
    pending = cs.iter_cuadernillos(only_pending=True)
    if materia:
        pending = [c for c in pending if c.materia_id == materia]
    if author_only:
        key = author_only.lower()
        pending = [c for c in pending if key in c.author_name.lower()]

    total_pending = len(pending)
    if limit and limit > 0:
        pending = pending[:limit]

    logger.info(
        "Cuadernillos pendientes: %d | a procesar ahora: %d | dry_run=%s",
        total_pending, len(pending), dry_run,
    )

    created = 0
    for i, item in enumerate(pending):
        try:
            if _process_one(item, dry_run=dry_run):
                created += 1
        except Exception:
            logger.exception("Error procesando %s", item.pseudo_url)
        if i < len(pending) - 1 and config.CUADERNILLOS_THROTTLE_SECONDS > 0:
            time.sleep(config.CUADERNILLOS_THROTTLE_SECONDS)

    logger.info("Listo. Cuadernillos generados en esta corrida: %d/%d", created, len(pending))
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador de posts por cuadernillo")
    parser.add_argument("--limit", type=int, default=config.CUADERNILLOS_MAX_PER_RUN,
                        help="Máximo a generar (0 = todos los pendientes)")
    parser.add_argument("--materia", default="", help="Filtra por id de materia (ej. campanas)")
    parser.add_argument("--author-only", default="", help="Filtra por autor (substring)")
    parser.add_argument("--dry-run", action="store_true", help="No publica ni marca estado")
    args = parser.parse_args()

    config.setup_logging()
    config.validate()
    logger.info("Iniciando generador de cuadernillos (DRY_RUN global=%s)", config.DRY_RUN)
    dry = args.dry_run or config.DRY_RUN
    try:
        run(limit=args.limit, materia=args.materia, author_only=args.author_only, dry_run=dry)
    except Exception:
        logger.exception("Error fatal en el generador de cuadernillos")
        sys.exit(1)


if __name__ == "__main__":
    main()
