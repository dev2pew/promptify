"""
PATH-AWARE MATCHING AND DISPLAY HELPERS FOR INDEXER SEARCH AND COMPLETIONS.
"""

from collections import defaultdict
from rapidfuzz import fuzz
from .settings import APP_SETTINGS

_PATH_SEPARATORS = "/._- "


def normalize_match_path(path: str) -> str:
    """NORMALIZES USER PATH INPUTS TO THE INTERNAL PROJECT FORMAT."""
    return path.replace("\\", "/").strip().strip("/")


def _path_leaf(path: str) -> str:
    """RETURNS THE FINAL PATH SEGMENT."""
    return path.rsplit("/", 1)[-1]


def _contains_boundary_match(text: str, query: str) -> bool:
    """CHECKS WHETHER A SUBSTRING STARTS AT A PATH-OR-WORD BOUNDARY."""
    start = text.find(query)
    while start != -1:
        if start == 0 or text[start - 1] in _PATH_SEPARATORS:
            return True
        start = text.find(query, start + 1)
    return False


def _subsequence_score(query: str, text: str) -> int:
    """SCORES ORDERED CHARACTER MATCHES WITH BONUSES FOR TIGHT, BOUNDARY HITS."""
    if not query:
        return 0

    score = 0
    cursor = 0
    prev_idx = -1

    for ch in query:
        idx = text.find(ch, cursor)
        if idx == -1:
            return -1

        score += 8
        if idx == 0 or text[idx - 1] in _PATH_SEPARATORS:
            score += 14
        if prev_idx != -1:
            if idx == prev_idx + 1:
                score += 12
            else:
                score -= min(idx - prev_idx - 1, 4)

        prev_idx = idx
        cursor = idx + 1

    return score


def path_candidate_matches(query: str, candidate: str) -> bool:
    """LIGHTWEIGHT FILTER DECIDING WHETHER A PATH IS A PLAUSIBLE MATCH."""
    normalized_query = normalize_match_path(query).lower()
    normalized_candidate = normalize_match_path(candidate).lower()

    if not normalized_query:
        return True
    if normalized_query in normalized_candidate:
        return True

    leaf = _path_leaf(normalized_candidate)
    query_tail = _path_leaf(normalized_query)

    if query_tail and query_tail in leaf:
        return True
    if (
        _subsequence_score(normalized_query, normalized_candidate)
        >= len(normalized_query) * 8
    ):
        return True
    if query_tail and _subsequence_score(query_tail, leaf) >= len(query_tail) * 8:
        return True
    settings = APP_SETTINGS.matching
    path_threshold = (
        settings.path_threshold_long
        if len(normalized_query) >= settings.query_length_switch
        else settings.path_threshold_short
    )
    leaf_threshold = (
        settings.leaf_threshold_long
        if len(query_tail) >= settings.query_length_switch
        else settings.leaf_threshold_short
    )
    if (
        fuzz.partial_ratio(normalized_query, normalized_candidate, processor=None)
        >= path_threshold
    ):
        return True
    if (
        query_tail
        and fuzz.partial_ratio(query_tail, leaf, processor=None) >= leaf_threshold
    ):
        return True

    return False


def _path_rank_key(query: str, candidate: str) -> tuple:
    """RETURNS AN ASCENDING SORT KEY SO STRONGER PATH MATCHES RISE FIRST."""
    normalized_query = normalize_match_path(query).lower()
    normalized_candidate = normalize_match_path(candidate).lower()
    leaf = _path_leaf(normalized_candidate)
    query_tail = _path_leaf(normalized_query)

    exact_path = normalized_candidate == normalized_query
    exact_leaf = leaf == normalized_query or (query_tail and leaf == query_tail)
    tail_match = bool(normalized_query) and normalized_candidate.endswith(
        normalized_query
    )
    leaf_prefix = bool(query_tail) and leaf.startswith(query_tail)
    path_prefix = bool(normalized_query) and normalized_candidate.startswith(
        normalized_query
    )
    leaf_boundary = bool(query_tail) and _contains_boundary_match(leaf, query_tail)
    path_boundary = bool(normalized_query) and _contains_boundary_match(
        normalized_candidate, normalized_query
    )
    leaf_subsequence = (
        _subsequence_score(query_tail, leaf)
        if query_tail
        else _subsequence_score("", "")
    )
    path_subsequence = _subsequence_score(normalized_query, normalized_candidate)
    leaf_partial = (
        fuzz.partial_ratio(query_tail, leaf, processor=None) if query_tail else 0
    )
    leaf_fuzzy = fuzz.WRatio(query_tail, leaf, processor=None) if query_tail else 0
    path_fuzzy = (
        fuzz.WRatio(normalized_query, normalized_candidate, processor=None)
        if normalized_query
        else 0
    )

    return (
        -int(exact_path),
        -int(exact_leaf),
        -int(tail_match),
        -int(leaf_prefix),
        -int(path_prefix),
        -int(leaf_boundary),
        -int(path_boundary),
        -leaf_subsequence,
        -path_subsequence,
        -leaf_partial,
        -leaf_fuzzy,
        -path_fuzzy,
        len(leaf),
        len(normalized_candidate),
        normalized_candidate,
    )


def rank_path_candidates(query: str, candidates: list[str]) -> list[str]:
    """SORTS CANDIDATES USING A PATH-FIRST HEURISTIC CLOSER TO FILE PICKERS."""
    normalized_query = normalize_match_path(query)
    unique_candidates = list(dict.fromkeys(normalize_match_path(c) for c in candidates))

    if not normalized_query:
        return sorted(unique_candidates, key=lambda c: c.lower())

    filtered = [c for c in unique_candidates if path_candidate_matches(query, c)]
    return sorted(filtered, key=lambda c: _path_rank_key(normalized_query, c))


def build_path_display_map(candidates: list[str]) -> dict[str, tuple[str, str]]:
    """BUILDS COMPACT LABELS AND PATH TAILS FOR COMPLETION MENUS."""
    normalized_candidates = list(
        dict.fromkeys(normalize_match_path(candidate) for candidate in candidates)
    )
    groups: dict[str, list[str]] = defaultdict(list)

    for candidate in normalized_candidates:
        groups[_path_leaf(candidate)].append(candidate)

    labels: dict[str, str] = {}
    for leaf, grouped_candidates in groups.items():
        if len(grouped_candidates) == 1:
            labels[grouped_candidates[0]] = leaf
            continue

        split_paths = {
            candidate: normalize_match_path(candidate).split("/")
            for candidate in grouped_candidates
        }
        max_depth = max(len(parts) for parts in split_paths.values())

        for depth in range(2, max_depth + 1):
            current = {
                candidate: "/".join(parts[-depth:])
                for candidate, parts in split_paths.items()
            }
            if len(set(current.values())) == len(grouped_candidates):
                labels.update(current)
                break
        else:
            for candidate in grouped_candidates:
                labels[candidate] = candidate

    display_map: dict[str, tuple[str, str]] = {}
    for candidate in normalized_candidates:
        label = labels[candidate]
        parts = candidate.split("/")
        label_parent_depth = label.count("/")
        parents = parts[:-1]
        if label_parent_depth:
            parents = parents[: max(0, len(parents) - label_parent_depth)]

        if parents:
            tail_segments = APP_SETTINGS.matching.display_meta_tail_segments
            tail = "/".join(parents[-tail_segments:])
            if len(parents) > tail_segments:
                tail = ".../" + tail
        else:
            tail = ""

        display_map[candidate] = (label, tail)

    return display_map
