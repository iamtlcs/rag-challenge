from __future__ import annotations

from collections import OrderedDict

from app.rag.models import Answer, RetrievalResult, SourceCitation
from app.rag.text import split_sentences


def _citations(results: list[RetrievalResult]) -> list[SourceCitation]:
    seen: OrderedDict[str, SourceCitation] = OrderedDict()
    for result in results:
        if result.url not in seen:
            seen[result.url] = SourceCitation(
                url=result.url,
                title=result.title,
                date=result.date,
                column=result.column,
                score=result.score,
            )
    return list(seen.values())


def compose_extractive_answer(
    question: str,
    results: list[RetrievalResult],
    *,
    max_sentences: int = 5,
) -> Answer:
    if not results:
        return Answer(
            answer=(
                "没有检索到足够相关的资料来可靠回答这个问题。"
                "请换一种问法，或确认索引已经完成全站抓取。"
            ),
            sources=[],
        )

    selected: list[str] = []
    for result in results:
        for sentence in split_sentences(result.text):
            if sentence not in selected:
                selected.append(sentence)
            if len(selected) >= max_sentences:
                break
        if len(selected) >= max_sentences:
            break

    evidence = " ".join(selected)
    top = results[0]
    answer = (
        "根据检索到的资料，"
        f"最相关来源是《{top.title}》"
        f"{f'（{top.date}）' if top.date else ''}。"
        f"{evidence}"
    )
    if question.strip():
        answer += " 以上回答仅基于列出的来源内容。"

    return Answer(answer=answer, sources=_citations(results))
