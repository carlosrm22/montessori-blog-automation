"""Persistent single-item queue for covers created manually in ChatGPT."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import secrets
import shutil
from contextlib import contextmanager
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import config
from content import GeneratedPost
from image_gen import build_full_cover_prompt

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
JOB_ID_RE = re.compile(r"^img-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$")
INPUT_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
JOB_STATUSES = frozenset(
    {"waiting_image", "image_prepared", "media_uploaded", "draft_created"}
)
STATUS_ORDER = {
    "waiting_image": 0,
    "image_prepared": 1,
    "media_uploaded": 2,
    "draft_created": 3,
}
JOB_KINDS = frozenset({"article", "cuadernillo"})
TERMINAL_STATUSES = frozenset({"published_draft", "cuadernillo_draft"})


class ManualImageQueueError(RuntimeError):
    """Base error for a queue operation that must fail closed."""


class PendingJobExists(ManualImageQueueError):
    """Raised when a second pending package would be created."""


class ManualImageNotReady(ManualImageQueueError):
    """Raised when no unambiguous input image exists for a job."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_root() -> Path:
    return config.MANUAL_IMAGE_QUEUE_DIR


def jobs_dir() -> Path:
    return queue_root() / "jobs"


def inbox_dir() -> Path:
    return queue_root() / "inbox"


def completed_dir() -> Path:
    return queue_root() / "completed"


def ensure_queue_dirs() -> None:
    for path in (queue_root(), jobs_dir(), inbox_dir(), completed_dir()):
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass


@contextmanager
def _queue_lock() -> Iterator[None]:
    ensure_queue_dirs()
    lock_path = queue_root() / ".lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _validate_job_id(job_id: str) -> str:
    clean = str(job_id or "").strip()
    if not JOB_ID_RE.fullmatch(clean):
        raise ManualImageQueueError("Identificador de trabajo inválido")
    return clean


def _pending_ids_unlocked() -> list[str]:
    if not jobs_dir().is_dir():
        return []
    return sorted(
        path.name
        for path in jobs_dir().iterdir()
        if path.is_dir() and JOB_ID_RE.fullmatch(path.name)
    )


def pending_job_ids() -> list[str]:
    with _queue_lock():
        return _pending_ids_unlocked()


def has_pending_job() -> bool:
    with _queue_lock():
        return bool(_pending_ids_unlocked())


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_job(path: Path, job: dict) -> None:
    serialized = json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(path, serialized)


def _validate_post_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ManualImageQueueError("El paquete no contiene un post válido")
    expected_fields = {field.name for field in fields(GeneratedPost)}
    if set(payload) != expected_fields:
        raise ManualImageQueueError("El contrato del post en cola no coincide")
    for name in ("categories", "tags"):
        value = payload.get(name)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ManualImageQueueError(f"Campo inválido en el post: {name}")
    for name in expected_fields - {"categories", "tags"}:
        if not isinstance(payload.get(name), str):
            raise ManualImageQueueError(f"Campo inválido en el post: {name}")


def validate_job(job: object, expected_job_id: str = "") -> dict:
    if not isinstance(job, dict):
        raise ManualImageQueueError("El archivo de trabajo no contiene un objeto JSON")
    if job.get("schema_version") != SCHEMA_VERSION:
        raise ManualImageQueueError("Versión de paquete manual no compatible")
    job_id = _validate_job_id(str(job.get("job_id", "")))
    if expected_job_id and job_id != _validate_job_id(expected_job_id):
        raise ManualImageQueueError("El ID interno no coincide con la carpeta del trabajo")
    if job.get("status") not in JOB_STATUSES:
        raise ManualImageQueueError("Estado de trabajo no válido")
    if job.get("kind") not in JOB_KINDS:
        raise ManualImageQueueError("Tipo de trabajo no válido")

    source = job.get("source")
    publication = job.get("publication")
    image = job.get("image")
    wordpress = job.get("wordpress")
    if not all(isinstance(value, dict) for value in (source, publication, image, wordpress)):
        raise ManualImageQueueError("El paquete manual está incompleto")
    for key in ("url", "title", "topic_id", "terminal_status"):
        if not isinstance(source.get(key), str) or not source.get(key).strip():
            raise ManualImageQueueError(f"Campo de fuente inválido: {key}")
    if source.get("terminal_status") not in TERMINAL_STATUSES:
        raise ManualImageQueueError("Estado terminal no permitido")
    try:
        float(source.get("score", 0.0))
    except (TypeError, ValueError) as exc:
        raise ManualImageQueueError("Puntaje de fuente inválido") from exc

    for key in (
        "topic_name",
        "author_name",
        "brand_id",
        "conversion_intent",
        "commercial_relevance",
        "destination_url",
    ):
        if not isinstance(publication.get(key), str):
            raise ManualImageQueueError(f"Campo de publicación inválido: {key}")
    for key in ("truseo_score", "headline_score"):
        value = publication.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= 100):
            raise ManualImageQueueError(f"Puntaje SEO inválido: {key}")

    for key in ("subject_prompt", "full_prompt", "alt_text", "expected_filename"):
        if not isinstance(image.get(key), str) or not image.get(key).strip():
            raise ManualImageQueueError(f"Campo de imagen inválido: {key}")
    if image.get("expected_filename") != f"{job_id}.png":
        raise ManualImageQueueError("Nombre esperado de imagen inválido")
    if not isinstance(image.get("input_name"), str):
        raise ManualImageQueueError("Nombre de imagen de entrada inválido")
    if image.get("input_name") != Path(image.get("input_name", "")).name:
        raise ManualImageQueueError("La imagen de entrada no puede contener una ruta")

    for key in ("media_id", "post_id"):
        value = wordpress.get(key)
        if value is not None and (type(value) is not int or value <= 0):
            raise ManualImageQueueError(f"ID de WordPress inválido: {key}")
    if wordpress.get("post_id") is not None and wordpress.get("media_id") is None:
        raise ManualImageQueueError("Un borrador manual no puede existir sin media_id")
    status = job["status"]
    media_id = wordpress.get("media_id")
    post_id = wordpress.get("post_id")
    if status == "waiting_image" and (media_id is not None or post_id is not None):
        raise ManualImageQueueError("waiting_image no admite IDs de WordPress")
    if status == "image_prepared":
        if not image.get("input_name"):
            raise ManualImageQueueError("image_prepared requiere una imagen de entrada")
        if media_id is not None or post_id is not None:
            raise ManualImageQueueError("image_prepared no admite IDs de WordPress")
    if status == "media_uploaded":
        if media_id is None:
            raise ManualImageQueueError("El estado media_uploaded requiere media_id")
        if post_id is not None:
            raise ManualImageQueueError("media_uploaded no admite post_id")
    if status == "draft_created" and (media_id is None or post_id is None):
        raise ManualImageQueueError(
            "El estado draft_created requiere media_id y post_id"
        )

    _validate_post_payload(job.get("post"))
    return job


def _load_job_unlocked(job_id: str) -> dict:
    clean_id = _validate_job_id(job_id)
    job_path = jobs_dir() / clean_id / "job.json"
    if not job_path.is_file():
        raise ManualImageQueueError(f"No existe el trabajo pendiente {clean_id}")
    try:
        raw = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualImageQueueError("No se pudo leer el paquete de trabajo") from exc
    return validate_job(raw, expected_job_id=clean_id)


def load_pending_job(job_id: str = "") -> dict:
    with _queue_lock():
        pending = _pending_ids_unlocked()
        if job_id:
            clean_id = _validate_job_id(job_id)
            if clean_id not in pending:
                raise ManualImageQueueError(f"No existe el trabajo pendiente {clean_id}")
        else:
            if not pending:
                raise ManualImageQueueError("No hay trabajos de portada pendientes")
            if len(pending) != 1:
                raise ManualImageQueueError("Hay más de un trabajo pendiente; se requiere revisión")
            clean_id = pending[0]
        return _load_job_unlocked(clean_id)


def job_directory(job_id: str) -> Path:
    return jobs_dir() / _validate_job_id(job_id)


def expected_input_path(job_id: str) -> Path:
    return inbox_dir() / f"{_validate_job_id(job_id)}.png"


def find_input_image(job_id: str) -> Path:
    clean_id = _validate_job_id(job_id)
    ensure_queue_dirs()
    candidates = sorted(
        path
        for path in inbox_dir().iterdir()
        if path.is_file()
        and path.stem == clean_id
        and path.suffix.lower() in INPUT_SUFFIXES
    )
    if not candidates:
        raise ManualImageNotReady(
            f"No hay imagen para {clean_id} en {inbox_dir()}"
        )
    if len(candidates) > 1:
        raise ManualImageNotReady(
            f"Hay varias imágenes para {clean_id}; deja solamente una"
        )
    return candidates[0]


def enqueue_manual_image(
    *,
    kind: str,
    source_url: str,
    source_title: str,
    source_score: float,
    topic_id: str,
    terminal_status: str,
    topic_name: str,
    author_name: str,
    brand_id: str,
    post: GeneratedPost,
    truseo_score: int | None,
    headline_score: int | None,
    conversion_intent: str,
    commercial_relevance: str,
    destination_url: str,
) -> dict:
    if kind not in JOB_KINDS:
        raise ManualImageQueueError("Tipo de trabajo manual no permitido")
    if terminal_status not in TERMINAL_STATUSES:
        raise ManualImageQueueError("Estado terminal manual no permitido")

    with _queue_lock():
        pending = _pending_ids_unlocked()
        if pending:
            raise PendingJobExists(
                f"Ya existe una portada pendiente: {pending[0]}"
            )

        now = datetime.now(timezone.utc)
        job_id = f"img-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"
        subject_prompt = (post.image_prompt or post.title).strip()
        full_prompt = build_full_cover_prompt(subject_prompt, brand_id=brand_id)
        job = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "status": "waiting_image",
            "kind": kind,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "source": {
                "url": str(source_url).strip(),
                "title": str(source_title).strip(),
                "score": float(source_score),
                "topic_id": str(topic_id).strip(),
                "terminal_status": terminal_status,
            },
            "publication": {
                "topic_name": str(topic_name).strip(),
                "author_name": str(author_name).strip(),
                "brand_id": str(brand_id).strip(),
                "truseo_score": truseo_score,
                "headline_score": headline_score,
                "conversion_intent": str(conversion_intent).strip(),
                "commercial_relevance": str(commercial_relevance).strip(),
                "destination_url": str(destination_url).strip(),
            },
            "post": asdict(post),
            "image": {
                "subject_prompt": subject_prompt,
                "full_prompt": full_prompt,
                "alt_text": post.image_alt_text,
                "expected_filename": f"{job_id}.png",
                "input_name": "",
            },
            "wordpress": {"media_id": None, "post_id": None},
        }
        validate_job(job, expected_job_id=job_id)

        staging = jobs_dir() / f".{job_id}.{secrets.token_hex(4)}.tmp"
        destination = jobs_dir() / job_id
        try:
            staging.mkdir(mode=0o700)
            _atomic_write_job(staging / "job.json", job)
            _atomic_write_text(staging / "prompt.txt", full_prompt + "\n")
            os.replace(staging, destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    logger.info("Trabajo de portada manual creado: %s", job_id)
    return job


def update_job_progress(
    job_id: str,
    *,
    status: str,
    media_id: int | None = None,
    post_id: int | None = None,
    input_name: str | None = None,
) -> dict:
    if status not in JOB_STATUSES:
        raise ManualImageQueueError("Estado de progreso no permitido")
    with _queue_lock():
        job = _load_job_unlocked(job_id)
        current_status = job["status"]
        current_position = STATUS_ORDER[current_status]
        next_position = STATUS_ORDER[status]
        if next_position < current_position:
            raise ManualImageQueueError("No se permite retroceder el estado del trabajo")
        if next_position > current_position + 1:
            raise ManualImageQueueError("No se permite omitir etapas del trabajo")

        current_media_id = job["wordpress"].get("media_id")
        current_post_id = job["wordpress"].get("post_id")
        if media_id is not None and current_media_id not in (None, media_id):
            raise ManualImageQueueError("No se permite cambiar el media_id existente")
        if post_id is not None and current_post_id not in (None, post_id):
            raise ManualImageQueueError("No se permite cambiar el post_id existente")

        job["status"] = status
        job["updated_at"] = _now()
        if media_id is not None:
            if type(media_id) is not int or media_id <= 0:
                raise ManualImageQueueError("media_id inválido")
            job["wordpress"]["media_id"] = media_id
        if post_id is not None:
            if type(post_id) is not int or post_id <= 0:
                raise ManualImageQueueError("post_id inválido")
            job["wordpress"]["post_id"] = post_id
        if input_name is not None:
            job["image"]["input_name"] = Path(input_name).name
        validate_job(job, expected_job_id=job_id)
        _atomic_write_job(job_directory(job_id) / "job.json", job)
        return job


def deserialize_post(job: dict) -> GeneratedPost:
    validated = validate_job(job, expected_job_id=str(job.get("job_id", "")))
    return GeneratedPost(**validated["post"])


def complete_job(job_id: str) -> Path:
    clean_id = _validate_job_id(job_id)
    with _queue_lock():
        job = _load_job_unlocked(clean_id)
        if job["status"] != "draft_created":
            raise ManualImageQueueError(
                "No se puede completar un trabajo antes de crear el borrador"
            )
        source = jobs_dir() / clean_id
        destination = completed_dir() / clean_id
        if destination.exists():
            raise ManualImageQueueError("El trabajo ya existe en el archivo completado")
        os.replace(source, destination)
    logger.info("Trabajo de portada completado: %s", clean_id)
    return destination
