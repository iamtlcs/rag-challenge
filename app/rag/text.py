from __future__ import annotations

import re
from typing import Any


SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_sentences(text: str) -> list[str]:
    clean = normalize_space(text)
    if not clean:
        return []
    sentences = [match.group(0).strip() for match in SENTENCE_RE.finditer(clean)]
    return [sentence for sentence in sentences if sentence]


def _join_sentences(sentences: list[str]) -> str:
    return "".join(sentences)


def chunk_text(
    record: dict[str, Any],
    *,
    max_chars: int = 900,
    overlap_sentences: int = 1,
) -> list[dict[str, Any]]:
    sentences = split_sentences(record.get("body", ""))
    if not sentences:
        return []

    chunks: list[dict[str, Any]] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        idx = len(chunks)
        chunks.append(
            {
                "chunk_id": f"{record.get('url', '')}#chunk-{idx}",
                "url": record.get("url", ""),
                "title": record.get("title", ""),
                "date": record.get("date", ""),
                "column": record.get("column", ""),
                "text": _join_sentences(current),
            }
        )

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                flush()
                current = current[-overlap_sentences:] if overlap_sentences else []
            for start in range(0, len(sentence), max_chars):
                part = sentence[start : start + max_chars]
                idx = len(chunks)
                chunks.append(
                    {
                        "chunk_id": f"{record.get('url', '')}#chunk-{idx}",
                        "url": record.get("url", ""),
                        "title": record.get("title", ""),
                        "date": record.get("date", ""),
                        "column": record.get("column", ""),
                        "text": part,
                    }
                )
            continue

        proposed = _join_sentences([*current, sentence])
        if current and len(proposed) > max_chars:
            flush()
            current = current[-overlap_sentences:] if overlap_sentences else []
        current.append(sentence)

    flush()
    return chunks
