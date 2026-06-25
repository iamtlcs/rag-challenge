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


def answer_question(
    question: str,
    results: list[RetrievalResult],
    *,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    max_context_chars: int = 9000,
) -> Answer:
    if not ollama_base_url or not ollama_model or not results:
        return compose_extractive_answer(question, results)

    try:
        import httpx

        context_parts: list[str] = []
        current_len = 0
        for idx, result in enumerate(results, start=1):
            block = (
                f"[{idx}] {result.title}\n"
                f"URL: {result.url}\n"
                f"Date: {result.date}\n"
                f"Column: {result.column}\n"
                f"{result.text}\n"
            )
            if current_len + len(block) > max_context_chars:
                break
            context_parts.append(block)
            current_len += len(block)

        context_text = "\n".join(context_parts)
        payload = {
            "model": ollama_model,
            "stream": False,
            "prompt": (
                "Answer only from the provided Tsinghua School of Software sources. "
                "Reply in the user's language when possible. Include brief source "
                "references like [1]. If evidence is insufficient, say so clearly.\n\n"
                f"Question:\n{question}\n\nSources:\n{context_text}"
            ),
        }
        response = httpx.post(
            f"{ollama_base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json().get("response", "")
        if content.strip():
            return Answer(answer=content.strip(), sources=_citations(results), mode="ollama")
    except Exception:
        pass

    return compose_extractive_answer(question, results)
