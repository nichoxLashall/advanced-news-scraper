from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())

def _split_sentences(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    sentences = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]

def _score_sentences(sentences: List[str], query_tokens: List[str]) -> List[Tuple[int, float]]:
    """
    Assign a relevance score to each sentence based on query term overlap.
    Returns a list of (index, score).
    """
    if not sentences:
        return []

    query_token_set = set(query_tokens)
    scores: List[Tuple[int, float]] = []

    for idx, sentence in enumerate(sentences):
        tokens = _tokenize(sentence)
        if not tokens:
            scores.append((idx, 0.0))
            continue

        token_counts = Counter(tokens)
        overlap = sum(token_counts[t] for t in query_token_set if t in token_counts)

        # Normalize by sentence length
        score = overlap / math.sqrt(len(tokens))
        scores.append((idx, score))

    return scores

def _compute_overall_score(scores: List[Tuple[int, float]]) -> int:
    """
    Convert sentence scores into a 0-100 relevance score.
    """
    if not scores:
        return 0

    raw_scores = [s for _, s in scores]
    max_score = max(raw_scores)
    if max_score <= 0:
        return 40  # low but non-zero baseline for unknown relevance

    avg_score = sum(raw_scores) / len(raw_scores)
    normalized = min(1.0, (avg_score / max_score))
    return int(50 + 50 * normalized)

def summarize(
    text: str,
    *,
    query: str,
    metadata_title: str | None = None,
    max_sentences: int = 3,
) -> Dict[str, Any]:
    """
    Generate a lightweight AI-style summary of the article text.

    This is intentionally simple and self-contained:
    - Splits the article into sentences.
    - Scores each sentence based on query term overlap.
    - Returns the top N sentences as a markdown bullet list.
    """
    text = text.strip()
    query_tokens = _tokenize(query)

    if not text:
        title = metadata_title or (query or "Untitled")
        return {
            "title": title,
            "summary": "",
            "score": 0,
        }

    sentences = _split_sentences(text)
    if not sentences:
        title = metadata_title or (query or "Untitled")
        return {
            "title": title,
            "summary": "",
            "score": 0,
        }

    scores = _score_sentences(sentences, query_tokens)
    sorted_by_score = sorted(scores, key=lambda x: x[1], reverse=True)

    # If every score is zero, fall back to the first few sentences in order.
    if all(score <= 0 for _, score in sorted_by_score):
        selected_indices = list(range(min(max_sentences, len(sentences))))
    else:
        top_indices = [idx for idx, _ in sorted_by_score[:max_sentences]]
        selected_indices = sorted(top_indices)

    bullets = [f"- {sentences[idx]}" for idx in selected_indices]
    summary_md = "\n".join(bullets)

    overall_score = _compute_overall_score(sorted_by_score)

    title = metadata_title or sentences[0][:120] or (query or "Untitled")

    return {
        "title": title,
        "summary": summary_md,
        "score": overall_score,
    }