"""Genera imagen de portada usando Gemini 2.5 Flash image generation."""

import io
import logging
import time
from pathlib import Path

from google import genai
from PIL import Image, ImageOps

import branding
import config

logger = logging.getLogger(__name__)

MODEL = config.GEMINI_IMAGE_MODEL
TARGET_SIZE = (config.WP_IMAGE_WIDTH, config.WP_IMAGE_HEIGHT)
JPEG_QUALITY = config.WP_IMAGE_QUALITY
MAX_IMAGE_BYTES = config.WP_IMAGE_MAX_KB * 1024


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
    full_prompt = branding.build_cover_prompt(
        subject_prompt=prompt,
        kit=kit,
        width=TARGET_SIZE[0],
        height=TARGET_SIZE[1],
    )

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
