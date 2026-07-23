"""Resume a queued article after its manually created cover is available."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

import config
import manual_image_queue as queue
import state
from image_gen import InvalidCoverImage, prepare_manual_cover_image
from notifier import notify_draft_created
from wordpress import (
    DraftLookupUnavailable,
    build_post_slug,
    create_draft,
    find_draft_by_slug,
    upload_media,
)

logger = logging.getLogger(__name__)


class ManualResumeError(RuntimeError):
    """Raised when resuming must stop without losing retryability."""


def _resolve_input(job_id: str, explicit_image: Path | None) -> Path:
    if explicit_image is not None:
        candidate = explicit_image.expanduser().resolve()
        if not candidate.is_file():
            raise queue.ManualImageNotReady(f"No existe la imagen indicada: {candidate}")
        return candidate
    return queue.find_input_image(job_id).resolve()


def _preserve_original(job_id: str, source: Path) -> None:
    suffix = source.suffix.lower()
    if suffix not in queue.INPUT_SUFFIXES:
        suffix = ".img"
    destination = queue.job_directory(job_id) / f"original{suffix}"
    try:
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
    except OSError as exc:
        logger.warning("No se pudo conservar una copia de la imagen original: %s", type(exc).__name__)


def _remove_consumed_inbox_image(job_id: str, source: Path | None) -> None:
    if source is None:
        return
    try:
        inbox = queue.inbox_dir().resolve()
        resolved = source.resolve()
        if resolved.parent == inbox and resolved.stem == job_id:
            resolved.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("No se pudo limpiar la imagen procesada del inbox: %s", type(exc).__name__)


def _recorded_inbox_image(job: dict) -> Path | None:
    """Recover the original inbox path after a process restart."""
    input_name = job.get("image", {}).get("input_name", "")
    if not input_name:
        return None
    candidate = queue.inbox_dir() / Path(input_name).name
    if candidate.is_file() and candidate.stem == job["job_id"]:
        return candidate.resolve()
    return None


def resume_manual_job(
    *,
    job_id: str = "",
    image_path: Path | None = None,
    if_ready: bool = False,
) -> int | None:
    """Complete one queued job, returning its WordPress draft ID."""
    if if_ready and not job_id and not queue.pending_job_ids():
        logger.info("No hay trabajos de portada pendientes.")
        return None

    job = queue.load_pending_job(job_id)
    resolved_job_id = job["job_id"]
    post = queue.deserialize_post(job)
    publication = job["publication"]
    wordpress = job["wordpress"]
    input_image = _recorded_inbox_image(job)

    media_id = wordpress.get("media_id")
    post_id = wordpress.get("post_id")
    prepared_path = queue.job_directory(resolved_job_id) / "cover.jpg"

    if post_id is None and media_id is None:
        if job["status"] == "image_prepared" and prepared_path.is_file():
            logger.info("Reutilizando portada ya preparada para %s", resolved_job_id)
        else:
            try:
                input_image = _resolve_input(resolved_job_id, image_path)
            except queue.ManualImageNotReady:
                if if_ready:
                    logger.info("La portada de %s todavía no está disponible.", resolved_job_id)
                    return None
                raise
            try:
                prepare_manual_cover_image(
                    input_image,
                    prepared_path,
                    brand_id=publication["brand_id"],
                )
            except InvalidCoverImage as exc:
                raise ManualResumeError(str(exc)) from exc
            _preserve_original(resolved_job_id, input_image)
            job = queue.update_job_progress(
                resolved_job_id,
                status="image_prepared",
                input_name=input_image.name,
            )

        media_id = upload_media(
            prepared_path,
            title=post.title,
            alt_text=post.image_alt_text,
            caption=post.excerpt or post.title,
            description=post.seo_description or post.excerpt,
        )
        if media_id is None:
            raise ManualResumeError(
                "WordPress no aceptó la portada; el trabajo permanece pendiente"
            )
        job = queue.update_job_progress(
            resolved_job_id,
            status="media_uploaded",
            media_id=media_id,
        )
    elif media_id is not None:
        logger.info("Reutilizando media_id=%d para %s", media_id, resolved_job_id)

    if media_id is None:
        raise ManualResumeError("El trabajo no tiene una imagen destacada válida")

    if post_id is None:
        try:
            post_id = find_draft_by_slug(
                build_post_slug(post),
                expected_media_id=media_id,
            )
        except DraftLookupUnavailable as exc:
            raise ManualResumeError(
                "No se pudo verificar si WordPress ya contiene el borrador; "
                "el trabajo permanece pendiente para evitar duplicados"
            ) from exc
        if post_id is not None:
            logger.warning(
                "Se encontró el borrador #%d con el mismo slug; se reutiliza para evitar duplicados.",
                post_id,
            )
        else:
            post_id = create_draft(
                post,
                media_id=media_id,
                author_name=publication["author_name"],
            )
        if post_id is None:
            raise ManualResumeError(
                "WordPress no creó el borrador; el trabajo permanece pendiente"
            )
        job = queue.update_job_progress(
            resolved_job_id,
            status="draft_created",
            post_id=post_id,
        )
    else:
        logger.info("Reutilizando post_id=%d para %s", post_id, resolved_job_id)

    source = job["source"]
    state.mark_processed(
        source["url"],
        title=post.title,
        score=float(source["score"]),
        wp_post_id=post_id,
        status=source["terminal_status"],
        topic_id=source["topic_id"],
    )
    queue.complete_job(resolved_job_id)
    _remove_consumed_inbox_image(resolved_job_id, input_image)

    notify_draft_created(
        post_id=post_id,
        title=post.title,
        topic_name=publication["topic_name"],
        author_name=publication["author_name"],
        edit_url=f"{config.WP_SITE_URL}/wp-admin/post.php?post={post_id}&action=edit",
        truseo_score=publication["truseo_score"],
        headline_score=publication["headline_score"],
        conversion_intent=publication["conversion_intent"],
        commercial_relevance=publication["commercial_relevance"],
        destination_url=publication["destination_url"],
    )
    logger.info(
        "Trabajo %s completado: borrador #%d creado con portada",
        resolved_job_id,
        post_id,
    )
    return post_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Procesa una portada manual y crea el borrador pendiente"
    )
    parser.add_argument("--job", default="", help="ID del trabajo; omite si solo hay uno")
    parser.add_argument("--image", type=Path, help="Ruta opcional de la imagen")
    parser.add_argument(
        "--if-ready",
        action="store_true",
        help="Finaliza correctamente si aún no existe la imagen",
    )
    args = parser.parse_args()

    config.setup_logging()
    config.validate()
    try:
        resume_manual_job(
            job_id=args.job,
            image_path=args.image,
            if_ready=args.if_ready,
        )
    except (queue.ManualImageQueueError, ManualResumeError) as exc:
        logger.error("No se pudo completar la portada manual: %s", exc)
        sys.exit(1)
    except Exception:
        logger.exception("Error inesperado al completar la portada manual")
        sys.exit(1)


if __name__ == "__main__":
    main()
