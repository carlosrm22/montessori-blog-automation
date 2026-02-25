"""Brand kit helpers for image prompt wrapping and postprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageEnhance
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
    return output
