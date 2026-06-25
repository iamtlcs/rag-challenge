from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

from app.standalone import build_documents_from_questions_html


TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style|noscript).*?</\1>", re.I | re.S)
CONTENT_MARKERS = ("v_news_content", "vsb_content", "article-render", "article-content", "news_content")
DATE_RE = re.compile(r"(20\d{2}|19\d{2})[-年./](\d{1,2})[-月./](\d{1,2})")


def strip_tags(fragment: str) -> str:
    fragment = SCRIPT_RE.sub(" ", fragment)
    fragment = re.sub(r"</p>|<br\s*/?>", "\n", fragment, flags=re.I)
    text = TAG_RE.sub(" ", fragment)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_article(url: str, html_text: str, fallback: dict[str, str]) -> dict[str, str]:
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.I | re.S)
    title = strip_tags(title_match.group(1)) if title_match else fallback.get("title", "")
    body = extract_body(html_text)
    date_match = DATE_RE.search(html_text)
    date = fallback.get("date", "")
    if date_match:
        date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    return {
        "url": url,
        "title": title or fallback.get("title", ""),
        "date": date,
        "column": fallback.get("column", ""),
        "body": body[:12000],
    }


def extract_body(html_text: str) -> str:
    marker_positions = [html_text.find(marker) for marker in CONTENT_MARKERS if html_text.find(marker) >= 0]
    if marker_positions:
        marker = min(marker_positions)
        start = max(html_text.rfind("<div", 0, marker), 0)
        fragment = html_text[start : start + 50000]
    else:
        fragment = html_text
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", fragment, re.I | re.S)
    if paragraphs:
        return "\n".join(strip_tags(paragraph) for paragraph in paragraphs if strip_tags(paragraph))
    return strip_tags(fragment)


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TKE-RAG-Challenge/1.0 article-cache-builder"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build article body cache from question source URLs.")
    parser.add_argument("--questions", type=Path, default=Path("html/questions.html"))
    parser.add_argument("--out", type=Path, default=Path("data/articles.json"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    docs = build_documents_from_questions_html(args.questions.read_text(encoding="utf-8"))
    if args.limit:
        docs = docs[: args.limit]
    articles = []
    if args.out.exists():
        articles = json.loads(args.out.read_text(encoding="utf-8"))
    seen = {article.get("url", "") for article in articles}
    for index, doc in enumerate(docs, start=1):
        url = doc["url"]
        if url in seen:
            print(f"[{index}/{len(docs)}] skip {url}")
            continue
        try:
            html_text = fetch(url, timeout=args.timeout)
            article = extract_article(url, html_text, doc)
            articles.append(article)
            seen.add(url)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[{index}/{len(docs)}] ok {url}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"[{index}/{len(docs)}] failed {url}: {exc}")
        if args.delay:
            time.sleep(args.delay)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(articles)} articles to {args.out}")


if __name__ == "__main__":
    main()
