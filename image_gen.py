"""Genera imagen de portada usando Gemini 2.5 Flash image generation."""

import io
import logging
import os
import time
import warnings
from pathlib import Path

from google import genai
from PIL import Image, ImageOps, UnidentifiedImageError

import branding
import config

logger = logging.getLogger(__name__)

MODEL = config.GEMINI_IMAGE_MODEL
TARGET_SIZE = (config.WP_IMAGE_WIDTH, config.WP_IMAGE_HEIGHT)
JPEG_QUALITY = config.WP_IMAGE_QUALITY
MAX_IMAGE_BYTES = config.WP_IMAGE_MAX_KB * 1024
ALLOWED_MANUAL_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
MIN_MANUAL_SIZE = (600, 315)


class InvalidCoverImage(ValueError):
    """Raised when a manually supplied cover cannot be accepted safely."""


def _is_zero_quota_error(exc: Exception) -> bool:
    message = str(exc)
    return "RESOURCE_EXHAUSTED" in message and "limit: 0" in message


def _prepare_cover_image(img: Image.Image) -> Image.Image:
    """Normalize orientation and fit target size without distortion."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    # Crop-to-fit keeps aspect ratio and avoids stretching.
    return ImageOps.fit(img, TARGET_SIZE, method=Image.LANCZOS, centering=(0.5, 0.5))


def _save_optimized_jpeg(img: Image.Image, output_path: Path) -> None:
    """Save optimized JPEG, reducing quality to fit max target size when possible."""
    quality = JPEG_QUALITY
    while quality >= 60:
        img.save(
            output_path,
            "JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        if output_path.stat().st_size <= MAX_IMAGE_BYTES:
            return
        quality -= 5
    # Final fallback keeps best effort even if size is above target.
    img.save(
        output_path,
        "JPEG",
        quality=60,
        optimize=True,
        progressive=True,
    )


def build_full_cover_prompt(prompt: str, brand_id: str | None = None) -> str:
    """Return the exact prompt used for a branded 1200x630 cover."""
    kit = branding.load_brand_kit(brand_id=brand_id)
    return branding.build_cover_prompt(
        subject_prompt=prompt,
        kit=kit,
        width=TARGET_SIZE[0],
        height=TARGET_SIZE[1],
    )


def prepare_manual_cover_image(
    input_path: Path,
    output_path: Path,
    brand_id: str | None = None,
) -> Path:
    """Validate, crop and optimize a user-supplied cover as a metadata-free JPEG."""
    source = Path(input_path).expanduser()
    destination = Path(output_path).expanduser()
    if not source.is_file():
        raise InvalidCoverImage(f"No existe el archivo de portada: {source}")
    if source.stat().st_size > config.MANUAL_IMAGE_MAX_MB * 1024 * 1024:
        raise InvalidCoverImage(
            f"La portada supera el límite de {config.MANUAL_IMAGE_MAX_MB} MB"
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                source_format = (opened.format or "").upper()
                if source_format not in ALLOWED_MANUAL_FORMATS:
                    raise InvalidCoverImage(
                        "Formato no admitido. Usa PNG, JPG/JPEG o WEBP."
                    )
                opened.load()
                source_size = opened.size
                if (
                    source_size[0] < MIN_MANUAL_SIZE[0]
                    or source_size[1] < MIN_MANUAL_SIZE[1]
                ):
                    raise InvalidCoverImage(
                        "La portada debe medir al menos "
                        f"{MIN_MANUAL_SIZE[0]}x{MIN_MANUAL_SIZE[1]} px"
                    )
                prepared = _prepare_cover_image(opened)
    except InvalidCoverImage:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidCoverImage("El archivo no es una imagen válida") from exc
    except Image.DecompressionBombError as exc:
        raise InvalidCoverImage("La imagen tiene dimensiones inseguras") from exc
    except Image.DecompressionBombWarning as exc:
        raise InvalidCoverImage("La imagen tiene dimensiones inseguras") from exc

    kit = branding.load_brand_kit(brand_id=brand_id)
    prepared = branding.apply_brand_look(prepared, kit)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        _save_optimized_jpeg(prepared, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    logger.info(
        "Portada manual preparada: %s (brand=%s, source=%dx%d -> %dx%d, %.1f KB)",
        destination,
        kit.brand_id,
        source_size[0],
        source_size[1],
        *TARGET_SIZE,
        destination.stat().st_size / 1024,
    )
    return destination


def generate_cover_image(
    prompt: str,
    output_dir: Path | None = None,
    max_retries: int = 3,
    brand_id: str | None = None,
) -> Path | None:
    """Generate a cover image and save as optimized JPEG. Returns path or None."""
    if not prompt:
        logger.warning("No image prompt provided, skipping image generation")
        return None

    output_dir = output_dir or config.IMAGES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    kit = branding.load_brand_kit(brand_id=brand_id)
    full_prompt = build_full_cover_prompt(prompt, brand_id=kit.brand_id)

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=full_prompt,
                config=genai.types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # Extract image from response parts
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    image_bytes = part.inline_data.data
                    source_img = Image.open(io.BytesIO(image_bytes))
                    source_size = source_img.size
                    img = _prepare_cover_image(source_img)
                    img = branding.apply_brand_look(img, kit)

                    timestamp = int(time.time())
                    output_path = output_dir / f"cover_{timestamp}.jpg"
                    _save_optimized_jpeg(img, output_path)

                    size_kb = output_path.stat().st_size / 1024
                    logger.info(
                        "Cover image saved: %s (brand=%s, source=%dx%d -> %dx%d, %.1f KB)",
                        output_path,
                        kit.brand_id,
                        source_size[0],
                        source_size[1],
                        *TARGET_SIZE,
                        size_kb,
                    )
                    return output_path

            logger.warning("Attempt %d: no image in response", attempt + 1)

        except Exception as exc:
            if _is_zero_quota_error(exc):
                logger.error(
                    "Image generation has zero quota for model %s; skipping retries",
                    MODEL,
                )
                return None
            wait = 2 ** (attempt + 1)
            logger.warning(
                "Image gen attempt %d/%d failed: %s. Retrying in %ds",
                attempt + 1, max_retries, exc, wait,
            )
            time.sleep(wait)

    logger.error("All %d image generation attempts failed", max_retries)
    return None


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    path = generate_cover_image(
        "A warm, inviting Montessori classroom with children engaged in "
        "hands-on learning activities, natural wood materials, plants"
    )
    print(f"Generated: {path}")
