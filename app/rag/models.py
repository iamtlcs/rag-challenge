from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    url: str
    title: str
    date: str
    column: str
    text: str
    score: float


@dataclass(frozen=True)
class SourceCitation:
    url: str
    title: str
    date: str
    column: str
    score: float


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[SourceCitation]
    mode: str = "extractive"


@dataclass
class RagIndex:
    vectorizer: Any
    matrix: Any
    chunks: list[dict[str, Any]]
