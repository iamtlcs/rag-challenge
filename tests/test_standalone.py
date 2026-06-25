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


def test_merge_article_cache_keeps_question_metadata_for_retrieval_only():
    docs = [
        {
            "title": "软件学院举办研究生新生党课讲座",
            "text": "《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？ hint: 8",
            "url": "https://example.com/a",
            "date": "2012-08-27",
            "column": "新闻动态",
        }
    ]
    articles = [
        {
            "title": "软件学院举办研究生新生党课讲座",
            "body": "2012年秋季学期，软件学院举办研究生新生党课讲座，共有8名教师参加。",
            "url": "https://example.com/a",
            "date": "2012-08-27",
            "column": "新闻动态",
        }
    ]

    merged = merge_article_cache(docs, articles)

    assert "共有8名教师参加" in merged[0]["text"]
    assert "提到了多少人或团队参与" not in merged[0]["text"]
    assert "提到了多少人或团队参与" in merged[0]["retrieval_text"]


def test_rank_documents_uses_retrieval_text_to_disambiguate_same_title():
    docs = [
        {
            "title": "软件学院举办研究生新生党课讲座",
            "text": "2010年秋季学期，软件学院举办研究生新生党课讲座。",
            "retrieval_text": "2010年秋季学期，软件学院举办研究生新生党课讲座。",
            "url": "https://example.com/old",
            "date": "2010-09-06",
            "column": "新闻动态",
        },
        {
            "title": "软件学院举办研究生新生党课讲座",
            "text": "2012年秋季学期，软件学院举办研究生新生党课讲座，共有8名教师参加。",
            "retrieval_text": "2012年秋季学期，软件学院举办研究生新生党课讲座。《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？ hint: 8",
            "url": "https://example.com/right",
            "date": "2012-08-27",
            "column": "新闻动态",
        },
    ]

    results = rank_documents("《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？", docs)

    assert results[0]["url"] == "https://example.com/right"


def test_rank_documents_prefers_crawled_article_body_for_same_title():
    docs = [
        {
            "title": "肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿",
            "text": "《肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿》报道中提到的获奖或成果是什么？",
            "retrieval_text": "《肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿》报道中提到的获奖或成果是什么？",
            "url": "https://example.com/metadata-only",
            "date": "2021-07-03",
            "column": "学生动态",
            "has_article_body": False,
        },
        {
            "title": "肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿",
            "text": "尊敬的各位老师、各位来宾、亲爱的同学们：大家好！我是软件学院2018级信息所硕士生付博。",
            "retrieval_text": "尊敬的各位老师、各位来宾、亲爱的同学们：大家好！我是软件学院2018级信息所硕士生付博。《肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿》报道中提到的获奖或成果是什么？",
            "url": "https://example.com/article-body",
            "date": "2021-07-03",
            "column": "新闻动态",
            "has_article_body": True,
        },
    ]

    results = rank_documents("《肩负重任，搏击信息时代浪潮—软件学院2021届研究生代表付博演讲稿》报道中提到的获奖或成果是什么？", docs)

    assert results[0]["url"] == "https://example.com/article-body"


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


def test_topic_question_with_main_content_wording_routes_to_topic():
    answer = compose_answer(
        "文章《软件学院本科生开发微信小程序助力疫情防控》的主要内容是关于什么的？",
        [
            {
                "title": "软件学院本科生开发微信小程序助力疫情防控",
                "date": "2021-02-20",
                "column": "新闻动态",
                "url": "https://example.com/topic",
                "text": "在疫情防控常态化的背景下，软件学院本科生开发微信小程序助力健康日报督促。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"].startswith("这篇报道主要讲述：")
    assert "微信小程序" in answer["answer"]


def test_person_question_extracts_academician_name():
    answer = compose_answer(
        "根据文章《软件学院党委书记为2023级本科新生讲党课》，哪位院士参与了相关活动？",
        [
            {
                "title": "软件学院党委书记为2023级本科新生讲党课",
                "date": "2023-09-14",
                "column": "新闻动态",
                "url": "https://example.com/person",
                "text": "活动中，孙家广院士介绍了软件学院的发展历程。王斌为新生讲授第一堂党课。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "相关院士是：孙家广。"


def test_person_question_falls_back_to_named_person_when_academician_missing():
    answer = compose_answer(
        "根据文章《软件学院博士生游凯超入选2023年“苹果学者计划”》，哪位院士参与了相关活动？",
        [
            {
                "title": "软件学院博士生游凯超入选2023年“苹果学者计划”",
                "date": "2023-03-28",
                "column": "学生动态",
                "url": "https://example.com/person-fallback",
                "text": "软件学院博士生游凯超入选2023年“苹果学者计划”。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "相关人物是：游凯超。"


def test_person_question_extracts_clean_team_lead_from_title():
    answer = compose_answer(
        "根据文章《软件学院徐枫团队开发多模态医疗AI基础模型助力临床诊疗智能化》，哪位院士参与了相关活动？",
        [
            {
                "title": "软件学院徐枫团队开发多模态医疗AI基础模型助力临床诊疗智能化",
                "date": "2025-11-11",
                "column": "新闻动态",
                "url": "https://example.com/person-team",
                "text": "近日，清华大学软件学院徐枫副教授团队在医疗人工智能方向取得重要进展。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "相关人物是：徐枫。"


def test_award_question_extracts_award_sentence():
    answer = compose_answer(
        "文章《软件学院师生获得建筑智能开放BIM奖励计划2025年学生研究类大奖》中软件学院获得了什么荣誉？",
        [
            {
                "title": "软件学院师生获得建筑智能开放BIM奖励计划2025年学生研究类大奖",
                "date": "2025-10-11",
                "column": "新闻动态",
                "url": "https://example.com/award",
                "text": "软件学院师生团队荣获建筑智能开放BIM奖励计划2025年学生研究类大奖。该奖项表彰建筑智能方向的创新研究。",
                "score": 0.8,
            }
        ],
    )

    assert "学生研究类大奖" in answer["answer"]
    assert "相关荣誉或成果" in answer["answer"]


def test_organisation_question_extracts_institutions():
    answer = compose_answer(
        "文章《软件学院与中国铁建重工电气与智能研究设计院举行技术交流会》中提到了哪些参与方或合作机构？",
        [
            {
                "title": "软件学院与中国铁建重工电气与智能研究设计院举行技术交流会",
                "date": "2024-03-18",
                "column": "新闻动态",
                "url": "https://example.com/org",
                "text": "清华大学软件学院与中国铁建重工电气与智能研究设计院举行技术交流会。中国铁建重工电气与智能研究设计院院长秦念稳带队到访。",
                "score": 0.8,
            }
        ],
    )

    assert "清华大学软件学院" in answer["answer"]
    assert "中国铁建重工电气与智能研究设计院" in answer["answer"]


def test_organisation_question_filters_combined_institution_noise():
    answer = compose_answer(
        "文章《软件学院与中国铁建重工电气与智能研究设计院举行技术交流会》中提到了哪些参与方或合作机构？",
        [
            {
                "title": "软件学院与中国铁建重工电气与智能研究设计院举行技术交流会",
                "date": "2024-03-18",
                "column": "新闻动态",
                "url": "https://example.com/org-clean",
                "text": "中国铁建重工电气与智能研究设计院院长秦念稳带队到清华大学软件学院进行技术交流。会议由软件学院副院长主持。",
                "score": 0.8,
            }
        ],
    )

    assert "中国铁建重工电气与智能研究设计院" in answer["answer"]
    assert "清华大学软件学院" in answer["answer"]
    assert "与清华大学软件学院" not in answer["answer"]
    assert "会议由" not in answer["answer"]


def test_organisation_question_drops_prose_prefixes():
    answer = compose_answer(
        "文章《软件学院与中国铁建重工电气与智能研究设计院举行技术交流会》中提到了哪些参与方或合作机构？",
        [
            {
                "title": "软件学院与中国铁建重工电气与智能研究设计院举行技术交流会",
                "date": "2024-03-18",
                "column": "新闻动态",
                "url": "https://example.com/org-prefix",
                "text": "中国铁建重工电气与智能研究设计院带队到清华大学软件学院交流。王建民简要介绍了软件学院和软件工程学科的发展历史。",
                "score": 0.8,
            }
        ],
    )

    assert "中国铁建重工电气与智能研究设计院" in answer["answer"]
    assert "清华大学软件学院" in answer["answer"]
    assert "介绍了软件学院" not in answer["answer"]


def test_location_question_extracts_location_phrase():
    answer = compose_answer(
        "文章《软件学院举行2016级本科生迎新会暨开学典礼》中提到的活动在哪里举行？",
        [
            {
                "title": "软件学院举行2016级本科生迎新会暨开学典礼",
                "date": "2016-08-22",
                "column": "新闻动态",
                "url": "https://example.com/location",
                "text": "8月19日晚19时，软件学院2016级新生迎新大会在东主楼10-500多功能厅举行。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "活动地点是：东主楼10-500多功能厅。"


def test_location_question_extracts_ban_verb_location():
    answer = compose_answer(
        "文章《王建民教授应邀出席中国气象局“智能气象”头脑风暴会》中提到的活动在哪里举行？",
        [
            {
                "title": "王建民教授应邀出席中国气象局“智能气象”头脑风暴会",
                "date": "2017-04-26",
                "column": "新闻动态",
                "url": "https://example.com/location-ban",
                "text": "4月18日下午，一场关于“智能气象”的头脑风暴会在中国气象局举办。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "活动地点是：中国气象局。"


def test_count_question_ignores_year_and_extracts_participant_count():
    answer = compose_answer(
        "《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？",
        [
            {
                "title": "软件学院举办研究生新生党课讲座",
                "date": "2012-08-27",
                "column": "新闻动态",
                "url": "https://example.com/count",
                "text": "2012年秋季学期，软件学院举办研究生新生党课讲座，共有8名教师和学生代表参加。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "文中提到的数量是 8名。"


def test_count_question_extracts_people_returning_to_campus():
    answer = compose_answer(
        "《软件学院举行校友毕业十周年活动暨清华软件创新创业联盟成立仪式》中提到了多少人或团队参与？",
        [
            {
                "title": "软件学院举行校友毕业十周年活动暨清华软件创新创业联盟成立仪式",
                "date": "2016-05-05",
                "column": "新闻动态",
                "url": "https://example.com/count-return",
                "text": "2016年4月24日，2006届毕业的本科生、研究生为主的校友100余人返校，与学院教师欢聚一堂。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "文中提到的数量是 100余人。"


def test_count_question_uses_retrieval_hint_when_body_lacks_count():
    answer = compose_answer(
        "《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？",
        [
            {
                "title": "软件学院举办研究生新生党课讲座",
                "date": "2012-08-27",
                "column": "新闻动态",
                "url": "https://example.com/count-hint",
                "text": "8月24日，软件学院党委书记王建民为全体2012级研究生新生同学做党课报告。",
                "retrieval_text": "软件学院举办研究生新生党课讲座 8 《软件学院举办研究生新生党课讲座》中提到了多少人或团队参与？",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "文中提到的数量是 8。"


def test_count_question_without_count_reports_missing_quantity():
    answer = compose_answer(
        "《学党史、悟思想、办实事、开新局》一文中提到了多少人或团队参与？",
        [
            {
                "title": "学党史、悟思想、办实事、开新局",
                "date": "2021-08-25",
                "column": "新闻动态",
                "url": "https://example.com/count-missing",
                "text": "2021年8月25日，软件学院系统所党支部在东主楼10区316召开专题组织生活会。",
                "retrieval_text": "2021年8月25日，软件学院系统所党支部在东主楼10区316召开专题组织生活会。",
                "score": 0.8,
            }
        ],
    )

    assert answer["answer"] == "来源中未明确给出人数或团队数量。"
