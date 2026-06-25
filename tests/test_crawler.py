from app.crawler import extract_article, extract_question_seed_urls


def test_extract_question_seed_urls_reads_embedded_questions_data():
    html = """
    <script>
    const QUESTIONS_DATA = [
      {"source_url": "https://www.thss.tsinghua.edu.cn/info/1023/1478.htm"},
      {"source_url": "https://www.thss.tsinghua.edu.cn/info/1023/1478.htm"},
      {"source_url": "https://www.thss.tsinghua.edu.cn/info/1024/2089.htm"}
    ];
    </script>
    """

    assert extract_question_seed_urls(html) == [
        "https://www.thss.tsinghua.edu.cn/info/1023/1478.htm",
        "https://www.thss.tsinghua.edu.cn/info/1024/2089.htm",
    ]


def test_extract_article_parses_title_date_body_and_images():
    html = """
    <html>
      <head><title>软件学院测试文章-清华大学软件学院</title></head>
      <body>
        <div class="localtion">当前位置： 首页 > 新闻动态</div>
        <h1>软件学院测试文章</h1>
        <span>发布时间：2025-06-03</span>
        <div class="v_news_content">
          <p>第一段介绍活动背景。</p>
          <p>第二段说明参与单位和成果。</p>
          <img src="../images/test.jpg" />
        </div>
      </body>
    </html>
    """

    article = extract_article(
        "https://www.thss.tsinghua.edu.cn/info/1023/2521.htm",
        html,
    )

    assert article["title"] == "软件学院测试文章"
    assert article["date"] == "2025-06-03"
    assert article["column"] == "新闻动态"
    assert "第一段介绍活动背景。" in article["body"]
    assert article["images"] == ["https://www.thss.tsinghua.edu.cn/info/1023/images/test.jpg"]
