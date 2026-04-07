"""Player name crosswalk for cross-source matching (VEG-03).

Provides standardize_name() for normalization and fuzzy_match() for
Levenshtein-based player name resolution across data sources (nflverse,
The Odds API, PFF).

Addresses HIGH review concern: player name matching must be robust across
name variants (Jr./III/apostrophes/nicknames).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Matches trailing suffixes: Jr., Sr., II, III, IV, V (case-insensitive)
_SUFFIX_PATTERN = re.compile(r"\s+(jr\.?|sr\.?|ii+|iv|v)\s*$", re.IGNORECASE)


def standardize_name(name: str) -> str:
    """Normalize a player name for cross-source matching.

    Transformations applied in order:
    1. Lowercase
    2. Remove periods (D.K. -> DK)
    3. Remove apostrophes, including curly/smart variants (Ja'Marr -> JaMarr)
    4. Strip suffixes: Jr., Sr., II, III, IV, V
    5. Strip leading/trailing whitespace, collapse internal whitespace

    Args:
        name: Raw player name from any data source.

    Returns:
        Normalized name suitable for matching across sources.
    """
    name = name.lower()
    # Remove periods
    name = name.replace(".", "")
    # Remove ASCII apostrophe, curly/right single quotation mark (U+2019), and backtick
    name = name.replace("'", "").replace("\u2019", "").replace("`", "")
    # Strip generation suffixes
    name = _SUFFIX_PATTERN.sub("", name)
    # Normalize whitespace
    return " ".join(name.split())


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Compute Levenshtein similarity ratio in [0.0, 1.0].

    1.0 means the strings are identical.  Uses standard DP algorithm.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Similarity ratio: 1.0 - (edit_distance / max_len).
    """
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    # Standard Levenshtein DP (single-row optimization)
    matrix = list(range(len2 + 1))
    for i in range(1, len1 + 1):
        prev = matrix[:]
        matrix[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            matrix[j] = min(prev[j] + 1, matrix[j - 1] + 1, prev[j - 1] + cost)

    distance = matrix[len2]
    max_len = max(len1, len2)
    return 1.0 - distance / max_len


def fuzzy_match(
    query: str,
    candidates: dict[str, str],
    threshold: float = 0.85,
) -> str | None:
    """Match a standardized name to the best candidate above threshold.

    Exact match is tried first (O(1) lookup).  If no exact match, Levenshtein
    ratios are computed for all candidates.

    Ambiguity guard: if the top-2 scores are within 0.05 of each other
    (could plausibly be either candidate), returns None and logs a warning.

    Args:
        query: Standardized player name to match.
        candidates: Dict of {standardized_name: player_id}.
        threshold: Minimum Levenshtein ratio to accept (default: 0.85).

    Returns:
        Best matching player_id above threshold, or None if no match or
        ambiguous match found.
    """
    if not candidates:
        return None

    # Exact match fast path
    if query in candidates:
        return candidates[query]

    best_id: str | None = None
    best_score = 0.0
    second_score = 0.0

    for name, pid in candidates.items():
        score = _levenshtein_ratio(query, name)
        if score > best_score:
            second_score = best_score
            best_score = score
            best_id = pid
        elif score > second_score:
            second_score = score

    if best_score < threshold:
        return None

    # Ambiguity guard: top two scores within 0.05 -> too close to call
    if best_score - second_score < 0.05:
        logger.warning(
            "Ambiguous player match for '%s': top two scores %.3f and %.3f (within 0.05) -- skipping",
            query,
            best_score,
            second_score,
        )
        return None

    return best_id
