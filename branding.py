"""Brand kit helpers for image prompt wrapping and postprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
import yaml

import config


@dataclass(frozen=True)
class BrandPostProcess:
    tint_hex: str = "#000000"
    tint_opacity: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0


@dataclass(frozen=True)
class BrandKit:
    brand_id: str
    display_name: str
    palette: dict[str, Any]
    prompt_prefix: str
    negative: str
    postprocess: BrandPostProcess
    logo: "BrandLogoSettings"


@dataclass(frozen=True)
class BrandLogoSettings:
    enabled: bool = False
    path: str = ""
    position: str = "bottom_right"
    scale: float = 0.14
    opacity: float = 0.16
    margin_px: int = 24


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = (hex_color or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return (0, 0, 0)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def load_brand_kit(brand_id: str | None = None) -> BrandKit:
    """Load one brand kit from YAML with resilient defaults."""
    chosen_brand = (brand_id or config.BRAND_KIT or "ammac").strip().lower()
    raw = yaml.safe_load(config.BRAND_KITS_FILE.read_text(encoding="utf-8")) or {}
    brands = raw.get("brands", {}) if isinstance(raw, dict) else {}

    resolved_brand = chosen_brand
    data = brands.get(chosen_brand) if isinstance(brands, dict) else None
    if not data and isinstance(brands, dict):
        if config.BRAND_KIT in brands:
            resolved_brand = config.BRAND_KIT
            data = brands.get(config.BRAND_KIT)
        elif "ammac" in brands:
            resolved_brand = "ammac"
            data = brands.get("ammac")
        elif brands:
            resolved_brand = next(iter(brands.keys()))
            data = brands.get(resolved_brand)
    if not isinstance(data, dict):
        data = {}
        resolved_brand = chosen_brand

    postprocess = data.get("postprocess", {}) if isinstance(data.get("postprocess", {}), dict) else {}
    logo_data = data.get("logo", {}) if isinstance(data.get("logo", {}), dict) else {}
    return BrandKit(
        brand_id=resolved_brand,
        display_name=str(data.get("display_name", resolved_brand or "brand")).strip(),
        palette=dict(data.get("palette", {}) or {}),
        prompt_prefix=str(data.get("prompt_prefix", "")).strip(),
        negative=str(data.get("negative", "")).strip(),
        postprocess=BrandPostProcess(
            tint_hex=str(postprocess.get("tint_hex", "#000000")).strip(),
            tint_opacity=max(0.0, min(1.0, _safe_float(postprocess.get("tint_opacity"), 0.0))),
            contrast=max(0.5, min(1.8, _safe_float(postprocess.get("contrast"), 1.0))),
            saturation=max(0.5, min(1.8, _safe_float(postprocess.get("saturation"), 1.0))),
        ),
        logo=BrandLogoSettings(
            enabled=bool(logo_data.get("enabled", False)),
            path=str(logo_data.get("path", "")).strip(),
            position=str(logo_data.get("position", "bottom_right")).strip().lower(),
            scale=_clamp(_safe_float(logo_data.get("scale"), 0.14), 0.05, 0.5),
            opacity=_clamp(_safe_float(logo_data.get("opacity"), 0.16), 0.05, 1.0),
            margin_px=max(0, _safe_int(logo_data.get("margin_px"), 24)),
        ),
    )


def _palette_tokens(palette: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for value in palette.values():
        if isinstance(value, str) and value.startswith("#"):
            tokens.append(value)
        elif isinstance(value, list):
            tokens.extend(item for item in value if isinstance(item, str) and item.startswith("#"))
    return tokens[:10]


def build_cover_prompt(subject_prompt: str, kit: BrandKit, width: int, height: int) -> str:
    """Build one prompt with style + palette + negative constraints."""
    ratio = round(width / max(height, 1), 2)
    palette_line = ""
    palette = _palette_tokens(kit.palette or {})
    if palette:
        palette_line = "Color palette (stay close to these tones): " + ", ".join(palette) + "."

    negative_line = ""
    if kit.negative:
        negative_line = f"Avoid: {kit.negative}."

    parts = [
        kit.prompt_prefix,
        palette_line,
        f"Subject: {subject_prompt.strip()}",
        negative_line,
        (
            f"High quality, realistic editorial image. "
            f"Wide aspect ratio {ratio}:1 for {width}x{height}. "
            "No text overlay."
        ),
    ]
    return "\n".join(part for part in parts if part and part.strip())


def apply_brand_look(img: Image.Image, kit: BrandKit) -> Image.Image:
    """Apply subtle brand color grading for visual consistency."""
    output = img.convert("RGB")
    pp = kit.postprocess

    if pp.tint_opacity > 0:
        tint = Image.new("RGB", output.size, _hex_to_rgb(pp.tint_hex))
        output = Image.blend(output, tint, pp.tint_opacity)

    if abs(pp.contrast - 1.0) > 1e-3:
        output = ImageEnhance.Contrast(output).enhance(pp.contrast)
    if abs(pp.saturation - 1.0) > 1e-3:
        output = ImageEnhance.Color(output).enhance(pp.saturation)
    return _apply_logo_overlay(output, kit.logo)


def _resolve_logo_path(raw_path: str) -> Path:
    logo_path = Path((raw_path or "").strip()).expanduser()
    if logo_path.is_absolute():
        return logo_path
    return (config.BASE_DIR / logo_path).resolve()


def _build_logo_alpha_channel(alpha: Image.Image, opacity: float) -> Image.Image:
    return alpha.point(lambda value: int(value * opacity))


def _logo_position(
    canvas_w: int,
    canvas_h: int,
    logo_w: int,
    logo_h: int,
    position: str,
    margin: int,
) -> tuple[int, int]:
    if position == "bottom_left":
        return (margin, canvas_h - logo_h - margin)
    if position == "top_right":
        return (canvas_w - logo_w - margin, margin)
    if position == "top_left":
        return (margin, margin)
    if position == "center":
        return ((canvas_w - logo_w) // 2, (canvas_h - logo_h) // 2)
    return (canvas_w - logo_w - margin, canvas_h - logo_h - margin)


def _apply_logo_overlay(img: Image.Image, logo_cfg: BrandLogoSettings) -> Image.Image:
    """Overlay one logo with conservative opacity and scale."""
    if not config.BRAND_LOGO_ENABLED:
        return img
    if not logo_cfg.enabled or not logo_cfg.path:
        return img

    logo_path = _resolve_logo_path(logo_cfg.path)
    if not logo_path.exists():
        return img

    try:
        logo = ImageOps.exif_transpose(Image.open(logo_path)).convert("RGBA")
    except Exception:
        return img

    canvas = img.convert("RGBA")
    target_width = max(1, int(canvas.width * logo_cfg.scale))
    if logo.width <= 0 or logo.height <= 0:
        return img
    ratio = target_width / logo.width
    target_height = max(1, int(logo.height * ratio))
    logo = logo.resize((target_width, target_height), Image.LANCZOS)

    alpha = logo.getchannel("A")
    logo.putalpha(_build_logo_alpha_channel(alpha, logo_cfg.opacity))

    x, y = _logo_position(
        canvas.width,
        canvas.height,
        logo.width,
        logo.height,
        logo_cfg.position,
        logo_cfg.margin_px,
    )
    x = max(0, min(canvas.width - logo.width, x))
    y = max(0, min(canvas.height - logo.height, y))
    canvas.alpha_composite(logo, dest=(x, y))
    return canvas.convert("RGB")
