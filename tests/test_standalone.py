from pathlib import Path

from app.standalone import (
    build_documents_from_questions_html,
    make_session_token,
    rank_documents,
    verify_session_token,
)


def test_standalone_builds_documents_from_questions_html():
    html = """
    <script>
    const QUESTIONS_DATA = [
      {
        "source_url": "https://www.thss.tsinghua.edu.cn/info/1023/2171.htm",
        "source_title": "软件学院党委书记为2023级本科新生讲党课",
        "source_date": "2023-09-14",
        "source_column": "新闻动态",
        "hint": "王斌为软件学院2023级本科新生讲授第一堂党课。",
        "question_zh": "主要讲述了哪方面的工作？",
        "question_en": "What aspect of work does the report describe?"
      }
    ];
    </script>
    """

    docs = build_documents_from_questions_html(html)

    assert docs[0]["title"] == "软件学院党委书记为2023级本科新生讲党课"
    assert "王斌" in docs[0]["text"]
    assert docs[0]["url"].endswith("/2171.htm")


def test_standalone_rank_documents_finds_relevant_result():
    docs = [
        {
            "title": "软件学院党委书记为2023级本科新生讲党课",
            "text": "王斌为软件学院2023级本科新生讲授第一堂党课。",
            "url": "https://example.com/a",
            "date": "2023-09-14",
            "column": "新闻动态",
        },
        {
            "title": "羽毛球比赛",
            "text": "学生参加羽毛球比赛。",
            "url": "https://example.com/b",
            "date": "",
            "column": "学生动态",
        },
    ]

    results = rank_documents("王斌 本科新生 党课", docs, top_k=2)

    assert results[0]["title"].startswith("软件学院党委书记")
    assert results[0]["score"] > results[1]["score"]


def test_standalone_session_token_round_trips():
    token = make_session_token("reviewer", "secret", now=100)

    assert verify_session_token(token, "secret", max_age=3600, now=200) == "reviewer"
    assert verify_session_token(token, "wrong", max_age=3600, now=200) is None
    assert verify_session_token(token, "secret", max_age=50, now=200) is None
