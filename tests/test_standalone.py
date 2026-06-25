from pathlib import Path

from app.standalone import (
    build_documents_from_questions_html,
    compose_answer,
    make_session_token,
    rank_documents,
    merge_article_cache,
    tokenize_bilingual,
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
            "text": "本科学生参加羽毛球比赛。",
            "url": "https://example.com/b",
            "date": "",
            "column": "学生动态",
        },
    ]

    results = rank_documents("王斌 本科新生 党课", docs, top_k=2)

    assert results[0]["title"].startswith("软件学院党委书记")
    assert results[0]["score"] > results[1]["score"]


def test_bilingual_tokenizer_keeps_english_words_dates_and_chinese_ngrams():
    tokens = tokenize_bilingual("What happened on 2023-09-14 软件学院讲党课?")

    assert "what" in tokens
    assert "2023-09-14" in tokens
    assert "软件" in tokens
    assert "党课" in tokens


def test_rank_documents_boosts_exact_title_and_date_matches():
    docs = [
        {
            "title": "软件学院师生获得2023建筑智能技术解决方案奖",
            "text": "获得了2023年技术解决方案奖。",
            "url": "https://example.com/wrong",
            "date": "2023-10-08",
            "column": "新闻动态",
        },
        {
            "title": "软件学院党委书记为2023级本科新生讲党课",
            "text": "9月10日，软件学院党委书记王斌为软件学院2023级本科新生讲授第一堂党课。",
            "url": "https://example.com/right",
            "date": "2023-09-14",
            "column": "新闻动态",
        },
    ]

    results = rank_documents("What happened on 2023-09-14 in 软件学院党委书记为2023级本科新生讲党课?", docs)

    assert results[0]["url"] == "https://example.com/right"


def test_rank_documents_prioritizes_exact_date_for_english_date_query():
    docs = [
        {
            "title": "Hybrid Transaction and Analytics Processing",
            "text": "IBM Fellow, database processing, analytics, School of Software seminar.",
            "url": "https://example.com/english",
            "date": "2019-01-11",
            "column": "新闻动态",
        },
        {
            "title": "软件学院党委书记为2023级本科新生讲党课",
            "text": "9月10日，软件学院党委书记王斌为软件学院2023级本科新生讲授第一堂党课。",
            "url": "https://example.com/date",
            "date": "2023-09-14",
            "column": "新闻动态",
        },
    ]

    results = rank_documents("What happened on 2023-09-14 at the School of Software?", docs)

    assert results[0]["url"] == "https://example.com/date"


def test_merge_article_cache_replaces_question_metadata_with_body_text():
    docs = [
        {
            "title": "软件学院党委书记为2023级本科新生讲党课",
            "text": "question metadata only",
            "url": "https://example.com/a",
            "date": "2023-09-14",
            "column": "新闻动态",
        }
    ]
    articles = [
        {
            "title": "软件学院党委书记为2023级本科新生讲党课",
            "body": "9月10日，软件学院党委书记王斌为软件学院2023级本科新生讲授第一堂党课。文章还介绍了理想信念教育。",
            "url": "https://example.com/a",
            "date": "2023-09-14",
            "column": "新闻动态",
        }
    ]

    merged = merge_article_cache(docs, articles)

    assert "理想信念教育" in merged[0]["text"]
    assert merged[0]["title"] == "软件学院党委书记为2023级本科新生讲党课"


def test_standalone_session_token_round_trips():
    token = make_session_token("reviewer", "secret", now=100)

    assert verify_session_token(token, "secret", max_age=3600, now=200) == "reviewer"
    assert verify_session_token(token, "wrong", max_age=3600, now=200) is None
    assert verify_session_token(token, "secret", max_age=50, now=200) is None


def test_standalone_date_question_returns_concise_date():
    answer = compose_answer(
        "On what date did the event in the article '软件学院师生代表参加国家示范性软件学院纪念表彰大会' occur?",
        [
            {
                "title": "软件学院师生代表参加国家示范性软件学院纪念表彰大会",
                "date": "2011-11-03",
                "column": "新闻动态",
                "url": "https://www.thss.tsinghua.edu.cn/info/1023/1478.htm",
                "text": "软件学院师生代表参加国家示范性软件学院纪念表彰大会 2011-11-03",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "事件发生日期是 2011-11-03。"


def test_standalone_topic_question_uses_hint_without_context_dump():
    answer = compose_answer(
        "《软件学院党委书记为2023级本科新生讲党课》这篇报道主要讲述了哪方面的工作？",
        [
            {
                "title": "软件学院党委书记为2023级本科新生讲党课",
                "date": "2023-09-14",
                "column": "新闻动态",
                "url": "https://www.thss.tsinghua.edu.cn/info/1023/2171.htm",
                "text": "软件学院党委书记为2023级本科新生讲党课 9月10日，软件学院党委书记王斌为软件学院2023级本科新生讲授第一堂党课。",
                "score": 0.8,
            }
        ],
    )

    assert "主要讲述" in answer["answer"]
    assert "王斌" in answer["answer"]
    assert "What aspect" not in answer["answer"]
