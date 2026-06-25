from app.rag.indexing import build_index
from app.rag.retriever import Retriever


def test_retriever_ranks_relevant_chinese_article_first():
    records = [
        {
            "url": "https://www.thss.tsinghua.edu.cn/info/1023/1.htm",
            "title": "软件学院举行人工智能论坛",
            "date": "2025-05-20",
            "column": "新闻动态",
            "body": "软件学院举行人工智能论坛，围绕大模型、知识检索和智能软件工程展开交流。",
        },
        {
            "url": "https://www.thss.tsinghua.edu.cn/info/1024/2.htm",
            "title": "学生羽毛球比赛",
            "date": "2025-05-21",
            "column": "学生动态",
            "body": "学生代表参加羽毛球比赛并获得冠军，活动在综合体育馆举行。",
        },
    ]
    index = build_index(records, chunk_chars=120, overlap_sentences=1)
    retriever = Retriever(index)

    results = retriever.search("软件学院 大模型 知识检索 论坛", top_k=2)

    assert results[0].title == "软件学院举行人工智能论坛"
    assert results[0].url.endswith("/1.htm")
    assert results[0].score > results[1].score
    assert "知识检索" in results[0].text


def test_retriever_returns_empty_list_for_blank_query():
    index = build_index(
        [
            {
                "url": "https://example.com/a",
                "title": "A",
                "date": "",
                "column": "",
                "body": "some content",
            }
        ]
    )

    assert Retriever(index).search("   ", top_k=3) == []
