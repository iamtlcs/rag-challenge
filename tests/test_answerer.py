from app.rag.answerer import compose_extractive_answer
from app.rag.models import RetrievalResult


def test_extractive_answer_mentions_evidence_and_sources():
    results = [
        RetrievalResult(
            chunk_id="u1#chunk-0",
            url="https://www.thss.tsinghua.edu.cn/info/1023/2171.htm",
            title="软件学院党委书记为2023级本科新生讲党课",
            date="2023-09-14",
            column="新闻动态",
            text="9月10日，软件学院党委书记王斌为软件学院2023级本科新生讲授第一堂党课。",
            score=0.82,
        )
    ]

    answer = compose_extractive_answer("这篇报道主要讲述了哪方面的工作？", results)

    assert "根据检索到的资料" in answer.answer
    assert "王斌" in answer.answer
    assert answer.sources[0].url.endswith("/2171.htm")
    assert answer.sources[0].title == "软件学院党委书记为2023级本科新生讲党课"


def test_extractive_answer_handles_no_evidence():
    answer = compose_extractive_answer("不存在的问题", [])

    assert "没有检索到足够相关的资料" in answer.answer
    assert answer.sources == []
