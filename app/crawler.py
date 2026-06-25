from __future__ import annotations

import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.rag.text import normalize_space


SOURCE_HOST = "www.thss.tsinghua.edu.cn"
USER_AGENT = "TKE-RAG-Challenge/1.0 polite crawler"
SOURCE_URL_RE = re.compile(r'"source_url"\s*:\s*"([^"]+)"')
DATE_RE = re.compile(
    r"(?:发布时间|发布日期|发表时间|时间|日期)\s*[:：]?\s*"
    r"([0-9]{4}[-年./][0-9]{1,2}[-月./][0-9]{1,2})"
)


def extract_question_seed_urls(html: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for raw in SOURCE_URL_RE.findall(html):
        url = raw.replace("\\/", "/")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _clean_title(title: str) -> str:
    return normalize_space(title).replace("-清华大学软件学院", "").strip()


def _normalize_date(raw: str) -> str:
    clean = raw.replace("年", "-").replace("月", "-").replace("日", "")
    clean = clean.replace("/", "-").replace(".", "-")
    parts = [part.zfill(2) if idx else part for idx, part in enumerate(clean.split("-"))]
    return "-".join(parts[:3])


def _extract_column(soup: BeautifulSoup) -> str:
    for node in soup.find_all(class_=re.compile(r"(localtion|location|position|breadcrumb)", re.I)):
        text = normalize_space(node.get_text(" "))
        if ">" in text:
            return normalize_space(text.split(">")[-1])
        if "：" in text:
            return normalize_space(text.split("：")[-1])
    text = normalize_space(soup.get_text(" "))
    match = re.search(r"当前位置[：:\s]*(?:首页\s*[>›]\s*)?([^>›\s]+)", text)
    return match.group(1) if match else ""


def _content_node(soup: BeautifulSoup) -> BeautifulSoup:
    selectors = [
        ".v_news_content",
        "#vsb_content",
        ".article-content",
        ".news_content",
        ".content",
        "article",
        "body",
    ]
    for selector in selectors:
        found = soup.select_one(selector)
        if found:
            return found
    return soup


def _resolve_asset_url(page_url: str, src: str) -> str:
    clean = (src or "").strip()
    if clean.startswith("../"):
        base_dir = page_url.rsplit("/", 1)[0] + "/"
        clean = clean.replace("../", "")
        return urljoin(base_dir, clean)
    return urljoin(page_url, clean)


def extract_article(url: str, html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    title_node = soup.find("h1")
    if title_node:
        title = _clean_title(title_node.get_text(" "))
    elif soup.title:
        title = _clean_title(soup.title.get_text(" "))
    else:
        title = ""

    all_text = normalize_space(soup.get_text(" "))
    date_match = DATE_RE.search(all_text)
    date = _normalize_date(date_match.group(1)) if date_match else ""

    content = _content_node(soup)
    paragraphs = [normalize_space(p.get_text(" ")) for p in content.find_all("p")]
    body = "\n".join(paragraph for paragraph in paragraphs if paragraph)
    if not body:
        body = normalize_space(content.get_text(" "))

    images = [
        _resolve_asset_url(url, img.get("src", ""))
        for img in content.find_all("img")
        if img.get("src")
    ]

    return {
        "url": url,
        "title": title,
        "date": date,
        "column": _extract_column(soup),
        "body": body,
        "images": images,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }


def _same_site(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == SOURCE_HOST


def extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        joined = urldefrag(urljoin(base_url, href))[0]
        if _same_site(joined) and joined not in seen:
            seen.add(joined)
            links.append(joined)
    return links


def crawl_urls(
    seeds: Iterable[str],
    *,
    max_pages: int = 900,
    delay: float = 0.75,
    timeout: float = 20.0,
) -> list[dict[str, object]]:
    queue = deque(url for url in seeds if _same_site(url))
    queued = set(queue)
    visited: set[str] = set()
    records: dict[str, dict[str, object]] = {}

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
        while queue and len(visited) < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue

            html = response.text
            if "/info/" in url and url.endswith(".htm"):
                article = extract_article(str(response.url), html)
                if article["title"] and len(str(article["body"])) > 40:
                    records[str(response.url)] = article

            for link in extract_links(str(response.url), html):
                if link not in queued and len(queued) < max_pages * 3:
                    queued.add(link)
                    queue.append(link)

            if delay:
                time.sleep(delay)

    return list(records.values())


def write_jsonl(records: Iterable[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
