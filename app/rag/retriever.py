from __future__ import annotations

import numpy as np

from app.rag.models import RagIndex, RetrievalResult


class Retriever:
    def __init__(self, index: RagIndex):
        self.index = index

    def search(self, query: str, *, top_k: int = 5) -> list[RetrievalResult]:
        if not query or not query.strip() or not self.index.chunks:
            return []

        query_vector = self.index.vectorizer.transform([query])
        scores = np.asarray((self.index.matrix @ query_vector.T).todense()).ravel()
        if scores.size == 0:
            return []
        if float(scores.max()) <= 0:
            return []

        ranked = np.argsort(scores)[::-1]
        results: list[RetrievalResult] = []
        for idx in ranked:
            score = float(scores[idx])
            chunk = self.index.chunks[int(idx)]
            results.append(
                RetrievalResult(
                    chunk_id=chunk["chunk_id"],
                    url=chunk["url"],
                    title=chunk["title"],
                    date=chunk.get("date", ""),
                    column=chunk.get("column", ""),
                    text=chunk["text"],
                    score=score,
                )
            )
            if len(results) >= top_k:
                break
        return results
