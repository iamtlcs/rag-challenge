from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer

from app.rag.models import RagIndex
from app.rag.text import chunk_text


INDEX_FILE = "rag_index.joblib"


def build_index(
    records: Iterable[dict[str, Any]],
    *,
    chunk_chars: int = 900,
    overlap_sentences: int = 1,
) -> RagIndex:
    chunks: list[dict[str, Any]] = []
    for record in records:
        chunks.extend(
            chunk_text(record, max_chars=chunk_chars, overlap_sentences=overlap_sentences)
        )

    texts = [chunk["text"] for chunk in chunks] or [""]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), lowercase=True)
    matrix = vectorizer.fit_transform(texts)
    if not chunks:
        matrix = matrix[:0]
    return RagIndex(vectorizer=vectorizer, matrix=matrix, chunks=chunks)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            clean = line.strip()
            if clean:
                records.append(json.loads(clean))
    return records


def save_index(index: RagIndex, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / INDEX_FILE
    joblib.dump(index, path)
    return path


def load_index(directory: Path) -> RagIndex:
    return joblib.load(directory / INDEX_FILE)


def index_exists(directory: Path) -> bool:
    return (directory / INDEX_FILE).exists()
