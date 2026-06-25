from app.rag.text import chunk_text, normalize_space, split_sentences


def test_normalize_space_collapses_mixed_whitespace():
    raw = " 清华大学软件学院\r\n\r\n  AI   实验室\t发布成果 "

    assert normalize_space(raw) == "清华大学软件学院 AI 实验室 发布成果"


def test_split_sentences_handles_chinese_and_english_punctuation():
    text = "软件学院举行开学典礼。Students joined the ceremony!地点在东主楼10-500。"

    assert split_sentences(text) == [
        "软件学院举行开学典礼。",
        "Students joined the ceremony!",
        "地点在东主楼10-500。",
    ]


def test_chunk_text_preserves_overlap_and_metadata():
    text = "第一段介绍背景。第二段介绍团队成员。第三段介绍获奖情况。第四段说明地点。"

    chunks = chunk_text(
        {
            "url": "https://www.thss.tsinghua.edu.cn/info/1023/9999.htm",
            "title": "软件学院测试文章",
            "date": "2026-06-25",
            "column": "新闻动态",
            "body": text,
        },
        max_chars=26,
        overlap_sentences=1,
    )

    assert len(chunks) >= 2
    assert chunks[0]["chunk_id"] == "https://www.thss.tsinghua.edu.cn/info/1023/9999.htm#chunk-0"
    assert chunks[0]["title"] == "软件学院测试文章"
    assert "第二段介绍团队成员。" in chunks[0]["text"]
    assert "第二段介绍团队成员。" in chunks[1]["text"]
