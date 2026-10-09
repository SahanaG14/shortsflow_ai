"""Local, dependency-free duplicate checks for proposed YouTube video ideas."""

import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

from duplicate_settings import (
    NEAR_TITLE_SIMILARITY_THRESHOLD,
    TITLE_TOKEN_WEIGHT,
    TOPIC_SIMILARITY_THRESHOLD,
)

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "is",
    "it", "of", "on", "or", "the", "this", "to", "what", "with", "you", "your",
}


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_accents.casefold()))


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[: -len(suffix)]
    return token


def _tokens(value: str) -> list[str]:
    return [
        _stem(token)
        for token in normalize_title(value).split()
        if token not in STOP_WORDS and len(token) > 1
    ]


def _title_similarity(left: str, right: str) -> float:
    left_normalized = normalize_title(left)
    right_normalized = normalize_title(right)
    sequence_score = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    token_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0.0
    return 0.65 * sequence_score + 0.35 * token_score


def _weighted_tokens(title: str, description: str) -> list[str]:
    return _tokens(title) * TITLE_TOKEN_WEIGHT + _tokens(description)


def _tfidf_cosine(proposed: list[str], documents: list[list[str]]) -> list[float]:
    """Compute lightweight local topic similarity without downloading a model."""
    document_frequency: Counter[str] = Counter()
    for document in [proposed, *documents]:
        document_frequency.update(set(document))
    document_count = len(documents) + 1

    def vector(tokens: list[str]) -> dict[str, float]:
        frequencies = Counter(tokens)
        return {
            token: frequency * (math.log((document_count + 1) / (document_frequency[token] + 1)) + 1)
            for token, frequency in frequencies.items()
        }

    proposed_vector = vector(proposed)
    proposed_norm = math.sqrt(sum(weight * weight for weight in proposed_vector.values()))
    scores: list[float] = []
    for document in documents:
        document_vector = vector(document)
        document_norm = math.sqrt(sum(weight * weight for weight in document_vector.values()))
        if not proposed_norm or not document_norm:
            scores.append(0.0)
            continue
        dot_product = sum(
            weight * document_vector.get(token, 0.0)
            for token, weight in proposed_vector.items()
        )
        scores.append(dot_product / (proposed_norm * document_norm))
    return scores


def check_duplicate(title: str, topic: str, videos: list[dict[str, str]]) -> dict[str, object]:
    """Classify a proposal against local video metadata in priority order."""
    normalized_title = normalize_title(title)
    if not normalized_title:
        return {
            "is_duplicate": False,
            "duplicate_type": "none",
            "similarity_score": 0.0,
            "matched_video_id": None,
            "matched_title": None,
            "reason": "Enter a proposed title or topic to check.",
        }

    for video in videos:
        if normalized_title == normalize_title(video["title"]):
            return {
                "is_duplicate": True,
                "duplicate_type": "exact_title",
                "similarity_score": 1.0,
                "matched_video_id": video["youtube_video_id"],
                "matched_title": video["title"],
                "reason": "The proposed title exactly matches an existing video title.",
            }

    if videos:
        title_scores = [_title_similarity(title, video["title"]) for video in videos]
        best_title_index = max(range(len(videos)), key=title_scores.__getitem__)
        if title_scores[best_title_index] >= NEAR_TITLE_SIMILARITY_THRESHOLD:
            match = videos[best_title_index]
            return {
                "is_duplicate": True,
                "duplicate_type": "similar_title",
                "similarity_score": round(title_scores[best_title_index], 3),
                "matched_video_id": match["youtube_video_id"],
                "matched_title": match["title"],
                "reason": "The proposed title is very similar to an existing title.",
            }

        proposed_tokens = _weighted_tokens(title, topic)
        topic_scores = _tfidf_cosine(
            proposed_tokens,
            [_weighted_tokens(video["title"], video["description"]) for video in videos],
        )
        best_topic_index = max(range(len(videos)), key=topic_scores.__getitem__)
        if topic_scores[best_topic_index] >= TOPIC_SIMILARITY_THRESHOLD:
            match = videos[best_topic_index]
            return {
                "is_duplicate": True,
                "duplicate_type": "similar_topic",
                "similarity_score": round(topic_scores[best_topic_index], 3),
                "matched_video_id": match["youtube_video_id"],
                "matched_title": match["title"],
                "reason": "The proposed topic overlaps strongly with an existing video's title or description.",
            }

    return {
        "is_duplicate": False,
        "duplicate_type": "none",
        "similarity_score": 0.0,
        "matched_video_id": None,
        "matched_title": None,
        "reason": "No exact, near-title, or similar-topic match was found.",
    }
