"""Conservative title novelty gate for recent WordPress content."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


_STOPWORDS = {
    "a", "al", "como", "con", "de", "del", "el", "en", "la", "las",
    "los", "para", "por", "un", "una", "y",
}


@dataclass(frozen=True)
class TitleQualityResult:
    accepted: bool
    highest_similarity: float
    matched_title: str


def _normalize(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.lower()))


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if token not in _STOPWORDS}


def _similarity(left: str, right: str) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    sequence = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return max(sequence, jaccard)


def check_title_novelty(
    candidate: str,
    existing_titles: list[str],
    threshold: float,
) -> TitleQualityResult:
    best_score = 0.0
    best_title = ""
    for index, title in enumerate(existing_titles):
        score = _similarity(candidate, title)
        if index == 0 or score > best_score:
            best_score = score
            best_title = title
    return TitleQualityResult(best_score < threshold, best_score, best_title)
