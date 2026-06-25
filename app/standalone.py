from __future__ import annotations

import base64
import hashlib
import hmac
import html
import http.cookies
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "html" / "questions.html"
ARTICLE_CACHE_PATH = ROOT / "data" / "articles.json"
COOKIE_NAME = "rag_session"
SOURCE_RE = re.compile(r"const\s+QUESTIONS_DATA\s*=\s*(\[.*?\]);", re.S)
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|\d{4}-\d{2}-\d{2}|\d+")
ORG_SUFFIX_RE = r"(?:大学|学院|研究设计院|研究院|公司|集团|委员会|中心|实验室|协会|学会|银行|医院|工作组|服务业司|司|部)"
ORG_CANDIDATE_RE = re.compile(
    rf"([\u4e00-\u9fffA-Za-z0-9（）()·\-]{{2,40}}{ORG_SUFFIX_RE})"
)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def build_documents_from_questions_html(html_text: str) -> list[dict[str, str]]:
    match = SOURCE_RE.search(html_text)
    if not match:
        return []
    rows = json.loads(match.group(1))
    docs_by_url: dict[str, dict[str, str]] = {}
    for row in rows:
        url = row.get("source_url", "")
        if not url:
            continue
        doc = docs_by_url.setdefault(
            url,
            {
                "url": url,
                "title": row.get("source_title", ""),
                "date": row.get("source_date", ""),
                "column": row.get("source_column", ""),
                "text": "",
            },
        )
        pieces = [
            row.get("source_title", ""),
            row.get("hint", ""),
            row.get("question_zh", ""),
            row.get("question_en", ""),
        ]
        doc["text"] = " ".join(part for part in [doc["text"], *pieces] if part).strip()
    return list(docs_by_url.values())


def load_article_cache(path: Path = ARTICLE_CACHE_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def merge_article_cache(
    docs: list[dict[str, str]],
    articles: list[dict[str, str]],
) -> list[dict[str, str]]:
    by_url = {article.get("url", ""): article for article in articles}
    merged: list[dict[str, str]] = []
    for doc in docs:
        article = by_url.get(doc.get("url", ""))
        if not article:
            metadata_doc = {**doc}
            metadata_doc.setdefault("retrieval_text", doc.get("text", ""))
            metadata_doc.setdefault("question_metadata", doc.get("text", ""))
            metadata_doc.setdefault("has_article_body", False)
            merged.append(metadata_doc)
            continue
        title = article.get("title") or doc.get("title", "")
        body = article.get("body") or article.get("text") or doc.get("text", "")
        answer_text = f"{title} {body}".strip()
        retrieval_text = " ".join(
            part for part in [answer_text, doc.get("text", "")] if part
        ).strip()
        merged.append(
            {
                "url": doc.get("url", ""),
                "title": title,
                "date": article.get("date") or doc.get("date", ""),
                "column": article.get("column") or doc.get("column", ""),
                "text": answer_text,
                "retrieval_text": retrieval_text,
                "question_metadata": doc.get("text", ""),
                "has_article_body": True,
            }
        )
    return merged


def tokenize_bilingual(text: str) -> list[str]:
    lowered = text.lower()
    tokens = WORD_RE.findall(lowered)
    for segment in CJK_RE.findall(text):
        if len(segment) == 1:
            tokens.append(segment)
            continue
        for n in (2, 3):
            if len(segment) >= n:
                tokens.extend(segment[i : i + n] for i in range(len(segment) - n + 1))
        if len(segment) <= 6:
            tokens.append(segment)
    return tokens


def rank_documents(query: str, docs: list[dict[str, str]], top_k: int = 5) -> list[dict[str, Any]]:
    query_tokens = tokenize_bilingual(query)
    if not query_tokens:
        return []
    query_dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", query))
    query_counts = Counter(query_tokens)
    doc_token_counts = []
    for doc in docs:
        weighted_tokens = []
        weighted_tokens.extend(tokenize_bilingual(doc.get("title", "")) * 3)
        weighted_tokens.extend(tokenize_bilingual(doc.get("date", "")) * 4)
        weighted_tokens.extend(tokenize_bilingual(doc.get("column", "")))
        weighted_tokens.extend(tokenize_bilingual(doc.get("retrieval_text") or doc.get("text", "")))
        doc_token_counts.append(Counter(weighted_tokens))
    doc_freq: Counter[str] = Counter()
    for counts in doc_token_counts:
        doc_freq.update(counts.keys())

    total_docs = max(len(docs), 1)
    ranked: list[dict[str, Any]] = []
    avg_len = sum(sum(counts.values()) for counts in doc_token_counts) / max(len(doc_token_counts), 1)
    for doc, counts in zip(docs, doc_token_counts):
        doc_len = max(sum(counts.values()), 1)
        if not counts:
            continue
        score = 0.0
        for token, qf in query_counts.items():
            tf = counts.get(token, 0)
            if not tf:
                continue
            idf = math.log(1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
            denom = tf + 1.2 * (1 - 0.75 + 0.75 * doc_len / max(avg_len, 1))
            score += idf * (tf * 2.2 / denom) * min(qf, 3)

        title = doc.get("title", "")
        date = doc.get("date", "")
        if title and title in query:
            score += 3.0
            if doc.get("has_article_body"):
                score += 100.0
        if date and date in query:
            score += 50.0 if query_dates else 1.5
        elif query_dates:
            score *= 0.35
        if score > 0:
            ranked.append({**doc, "score": score})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def make_session_token(username: str, secret: str, now: int | None = None) -> str:
    issued = str(now if now is not None else int(time.time()))
    body = f"{username}:{issued}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}:{sig}".encode()).decode()


def verify_session_token(
    token: str,
    secret: str,
    *,
    max_age: int = 60 * 60 * 12,
    now: int | None = None,
) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        username, issued, sig = decoded.rsplit(":", 2)
        body = f"{username}:{issued}"
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        current = now if now is not None else int(time.time())
        if current - int(issued) > max_age:
            return None
        return username
    except Exception:
        return None


def compose_answer(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    ollama_answer = ask_ollama(question, results)
    if ollama_answer:
        return {"answer": ollama_answer, "mode": "ollama", "sources": source_payload(results)}
    if not results:
        return {
            "answer": "没有检索到足够相关的资料来可靠回答这个问题。请换一种问法。",
            "mode": "local-extractive",
            "sources": [],
        }
    top = results[0]
    answer = direct_answer(question, top)
    return {"answer": answer, "mode": "local-extractive", "sources": source_payload(results)}


def direct_answer(question: str, top: dict[str, Any]) -> str:
    normalized = question.lower()
    title = top.get("title", "")
    date = top.get("date", "")
    raw_text = str(top.get("text", ""))
    text = clean_evidence_text(raw_text, title)

    asks_person = (
        "哪位" in question
        or "who" in normalized
        or "person" in normalized
        or "院士" in question
        or "academician" in normalized
    )
    if asks_person:
        person_text = f"{title} {text}"
        academician_only = "院士" in question or "academician" in normalized
        people = extract_people(person_text, academician_only=academician_only)
        if people:
            label = "相关院士" if academician_only else "相关人物"
            return f"{label}是：{'、'.join(people)}。"
        if academician_only:
            people = extract_people(title) or extract_people(text)
            if people:
                return f"相关人物是：{'、'.join(people)}。"

    if date and (
        "what date" in normalized
        or "when" in normalized
        or "哪一天" in question
        or "什么时候" in question
        or "日期" in question
    ):
        return f"事件发生日期是 {date}。"

    if (
        "主要讲述" in question
        or "主要内容" in question
        or "关于什么" in question
        or "mainly describe" in normalized
        or "what aspect" in normalized
        or "main content" in normalized
    ):
        evidence = first_good_sentence(text) or title
        return f"这篇报道主要讲述：{evidence}"

    if "在哪里" in question or "where" in normalized:
        location = extract_location(text)
        if location:
            return f"活动地点是：{location}。"
        evidence = first_good_sentence(text) or "来源中未给出明确地点"
        return f"相关地点信息：{evidence}"

    if "多少" in question or "how many" in normalized:
        count = extract_count(text) or extract_count_hint(
            str(top.get("question_metadata") or top.get("retrieval_text", ""))
        )
        if count:
            return f"文中提到的数量是 {count}。"
        return "来源中未明确给出人数或团队数量。"

    if "荣誉" in question or "获奖" in question or "honor" in normalized or "award" in normalized:
        evidence = extract_award(text) or first_good_sentence(text) or title
        return f"相关荣誉或成果是：{evidence}"

    if (
        "参与方" in question
        or "合作机构" in question
        or "institution" in normalized
        or "participating parties" in normalized
        or "org" in normalized
    ):
        organisations = extract_organisations(raw_text, title)
        if organisations:
            return f"提到的参与方或合作机构包括：{'、'.join(organisations)}。"

    evidence = first_good_sentence(text) or text[:180] or title
    suffix = f" 来源：《{title}》" if title else ""
    return f"{evidence}{suffix}"


def extract_people(text: str, *, academician_only: bool = False) -> list[str]:
    if academician_only:
        patterns = [r"([\u4e00-\u9fff]{2,4})院士"]
    else:
        boundary = r"(?=$|[，。、“”\s]|入选|获得|荣获|参加|作为|和)"
        patterns = [
            r"([\u4e00-\u9fff]{2,4})院士",
            rf"(?:博士生|学生|教授|副教授|院长|书记)([\u4e00-\u9fff]{{2,3}}){boundary}",
            rf"([\u4e00-\u9fff]{{2,3}})(?:教授|副教授|书记|院长|同学|老师){boundary}",
            r"([\u4e00-\u9fff]{2,3})团队",
            rf"([\u4e00-\u9fff]{{2,3}})作为{boundary}",
            rf"导师为([\u4e00-\u9fff]{{2,3}}){boundary}",
        ]
    stop_names = {
        "软件学院",
        "清华大学",
        "人工智能",
        "智能",
        "学院",
        "学校",
        "团队",
        "医院",
        "第一医院",
    }
    names: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            match = re.sub(r"(入选|获得|荣获|参加|作为|入|获|为|作)$", "", match)
            match = match.strip("与和及")
            if len(match) == 3 and match[0] in "院件学系校所":
                match = match[1:]
            if len(match) == 3 and match[-1] in "与和及":
                match = match[:-1]
            if (
                match not in names
                and match not in stop_names
                and not any(word in match for word in ("学院", "大学", "人工", "智能", "医院"))
            ):
                names.append(match)
    return names[:5]


def extract_location(text: str) -> str | None:
    location_patterns = [
        r"在([^，。；;]{2,35}(?:楼|厅|室|馆|中心|大学|校区|园|会议室|报告厅|多功能厅))举行",
        r"在([^，。；;]{2,35}(?:楼|厅|室|馆|中心|大学|校区|园|会议室|报告厅|多功能厅))召开",
        r"在([^，。；;]{2,35}(?:楼|厅|室|馆|中心|大学|校区|园|局|会议室|报告厅|多功能厅))举办",
        r"于([^，。；;]{2,35}(?:楼|厅|室|馆|中心|大学|校区|园|会议室|报告厅|多功能厅))举行",
        r"地点(?:为|是|：|:)([^，。；;]{2,35})",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def extract_count(text: str) -> str | None:
    unit = r"(?:余?名|余?人|人|位|个|支|项|团队|队伍)"
    patterns = [
        rf"(?:共有|共|约|邀请|组织|吸引|参加|参与|出席)[^\d一二三四五六七八九十百千万]{{0,8}}(\d+)\s*({unit})",
        rf"(\d+)\s*({unit})(?:[^，。；;]{{0,12}}(?:参加|参与|出席|团队|返校|到场|参会|欢聚))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    return None


def extract_count_hint(text: str) -> str | None:
    for match in re.finditer(r"(?<!\d)(\d{1,3})(?!\d)", text):
        number = match.group(1)
        if number == "0":
            continue
        context = text[max(0, match.start() - 4) : match.end() + 4]
        if re.search(rf"(?:区|楼|室|教室)\s*{number}|{number}\s*(?:年|月|日|级|届|区|楼|室|教室|点)", context):
            continue
        return number
    return None


def extract_award(text: str) -> str | None:
    for sentence in split_sentences(text):
        if re.search(r"荣获|获得|获|入选|一等奖|二等奖|三等奖|特等奖|大奖|冠军|奖项|成果", sentence):
            return sentence
    return None


def extract_organisations(text: str, title: str = "") -> list[str]:
    organisations: list[str] = []

    def add_candidate(candidate: str) -> None:
        for piece in split_org_candidate(candidate):
            item = trim_org_phrase(piece)
            if not item:
                continue
            if any(item == known or item in known for known in organisations):
                continue
            organisations[:] = [known for known in organisations if known not in item]
            organisations.append(item)

    for sentence in split_sentences(f"{title}。{text}"):
        for match in ORG_CANDIDATE_RE.findall(sentence):
            add_candidate(match)
    return organisations[:6]


def split_org_candidate(text: str) -> list[str]:
    parts: list[str] = []
    remaining = text.strip()
    while re.search(r"[与和及]", remaining):
        split_at = None
        for match in re.finditer(r"[与和及]", remaining):
            left = remaining[: match.start()].strip(" ，。；;、")
            if re.search(ORG_SUFFIX_RE + r"$", left):
                split_at = match.start()
                break
        if split_at is None:
            break
        parts.append(remaining[:split_at])
        remaining = remaining[split_at + 1 :].strip()
    if remaining:
        parts.append(remaining)
    return parts or [text]


def trim_org_phrase(text: str) -> str:
    clean = re.sub(r"^[，。；;、与和及\s]*(?:文章|报道|活动中|近日|来自|邀请|由|会议由)?", "", text)
    clean = re.sub(
        r"^.*?(?:培训对|简要介绍了|介绍了|讲解了|作为主题详细分享了|详细分享了|分享了|汇报了)",
        "",
        clean,
    )
    clean = re.sub(r"^(?:在|为|对|本次|此次|通过|推进|提升|组织|培训|相关技术和)+", "", clean)
    destination = re.search(
        rf"(?:到|赴)([\u4e00-\u9fffA-Za-z0-9（）()·\-]{{2,40}}{ORG_SUFFIX_RE})$",
        clean,
    )
    if destination:
        clean = destination.group(1)
    clean = re.split(
        r"(?:成立大会|大会|第一次|举行|召开|开展|访问|带队|院长|书记|教授|副司长|司长|副司|参加|主办|承办|合作|交流)",
        clean,
    )[0]
    clean = clean.strip(" ，。；;、与和及")
    clean = re.sub(
        rf"^.*?(清华大学软件学院|[\u4e00-\u9fffA-Za-z0-9（）()·\-]{{2,40}}{ORG_SUFFIX_RE})$",
        r"\1",
        clean,
    )
    if clean in {"学院", "大学", "研究院", "中心"}:
        return ""
    return clean if len(clean) >= 2 else ""


def clean_evidence_text(text: str, title: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if title:
        clean = clean.replace(title, " ")
    clean = re.sub(r"What aspect.*?(?:describe\?|$)", " ", clean)
    clean = re.sub(r"On what date.*?(?:occur\?|$)", " ", clean)
    clean = re.sub(r"Where was.*?(?:held\?|$)", " ", clean)
    clean = re.sub(r"What honor.*?(?:receive\?|$)", " ", clean)
    clean = re.sub(r"《\s*》报道中[^？]*？", " ", clean)
    clean = re.sub(r"文章《[^》]+》[^？]*？", " ", clean)
    clean = re.sub(r"《[^》]+》这篇报道[^？]*？", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？!?])\s*", text) if part.strip()]


def first_good_sentence(text: str) -> str:
    for clean in split_sentences(text):
        if clean and len(clean) >= 8:
            return clean
    return text.strip()


def source_payload(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    sources = []
    for item in results:
        url = item.get("url", "")
        if url in seen:
            continue
        seen.add(url)
        sources.append(
            {
                "url": url,
                "title": item.get("title", ""),
                "date": item.get("date", ""),
                "column": item.get("column", ""),
                "score": item.get("score", 0),
            }
        )
    return sources


def ask_ollama(question: str, results: list[dict[str, Any]]) -> str | None:
    base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not base_url or not model or not results:
        return None
    context = "\n\n".join(
        f"[{idx}] {item.get('title')}\n{item.get('text', '')[:1200]}"
        for idx, item in enumerate(results[:5], start=1)
    )
    payload = {
        "model": model,
        "stream": False,
        "prompt": (
            "Answer from the provided Tsinghua School of Software sources. "
            "Use Chinese when the question is Chinese. Cite source numbers.\n\n"
            f"Question: {question}\n\nSources:\n{context}"
        ),
    }
    try:
        req = urllib.request.Request(
            urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/generate"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        answer = data.get("response", "").strip()
        return answer or None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


class RagHandler(BaseHTTPRequestHandler):
    docs: list[dict[str, str]] = []
    username = "reviewer"
    password = "change-me"
    secret = "dev-secret"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.json_response({"status": "ok", "index_ready": bool(self.docs), "document_count": len(self.docs)})
            return
        if self.path.startswith("/challenge/"):
            self.serve_file(ROOT / "html" / self.path.removeprefix("/challenge/"))
            return
        self.html_response(render_page())

    def do_POST(self) -> None:
        if self.path == "/api/login":
            payload = self.read_json()
            if payload.get("username") == self.username and payload.get("password") == self.password:
                token = make_session_token(self.username, self.secret)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Lax; Path=/")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return
            self.json_response({"detail": "Invalid username or password"}, HTTPStatus.UNAUTHORIZED)
            return
        if self.path == "/api/logout":
            self.send_response(HTTPStatus.OK)
            self.send_header("Set-Cookie", f"{COOKIE_NAME}=; Max-Age=0; Path=/")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return
        if self.path == "/api/chat":
            if not self.current_user():
                self.json_response({"detail": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
                return
            payload = self.read_json()
            message = str(payload.get("message", "")).strip()
            results = rank_documents(message, self.docs, top_k=int(os.getenv("RAG_TOP_K", "5")))
            self.json_response(compose_answer(message, results))
            return
        self.json_response({"detail": "Not found"}, HTTPStatus.NOT_FOUND)

    def current_user(self) -> str | None:
        cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        if not morsel:
            return None
        return verify_session_token(morsel.value, self.secret)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def html_response(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.resolve().is_relative_to((ROOT / "html").resolve()):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def render_page() -> str:
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TKE RAG Chat</title><style>
body{margin:0;background:#10141f;color:#edf2f7;font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{min-height:100vh;display:grid;grid-template-columns:320px 1fr}.side{padding:28px;background:#151b27;border-right:1px solid #2b3446}
.main{display:grid;grid-template-rows:auto 1fr auto;height:100vh}.head,.composer{padding:18px 24px;border-bottom:1px solid #2b3446;display:flex;gap:12px;align-items:center}
.messages{overflow:auto;padding:24px;display:flex;flex-direction:column;gap:12px}.msg{max-width:850px;padding:13px 15px;border-radius:8px;white-space:pre-wrap;line-height:1.55}
.user{align-self:flex-end;background:#64d2a6;color:#061018}.bot{align-self:flex-start;background:#1b2332;border:1px solid #2b3446}
input,textarea{background:#0d1320;color:#edf2f7;border:1px solid #2b3446;border-radius:8px;padding:12px;font:inherit}button{border:0;border-radius:8px;background:#37b3ff;color:#071018;font-weight:800;padding:12px 18px;cursor:pointer}
#login{max-width:420px;margin:15vh auto;padding:28px;background:#151b27;border:1px solid #2b3446;border-radius:8px}.hidden{display:none}.source{font-size:13px;margin:8px 0;padding:10px;border:1px solid #2b3446;border-radius:8px}.source a{color:#37b3ff}
@media(max-width:800px){.wrap{grid-template-columns:1fr}.side{display:none}}
</style></head><body>
<section id="login"><h1>TKE RAG Chat</h1><p>Local open-source retrieval, no paid API key.</p><input id="u" placeholder="Username"><br><br><input id="p" type="password" placeholder="Password"><br><br><button onclick="login()">Sign in</button><p id="e"></p></section>
<section id="app" class="wrap hidden"><aside class="side"><h2>清华大学软件学院</h2><p id="health">Checking...</p><div id="sources"></div><a style="color:#37b3ff" href="/challenge/questions.html" target="_blank">Question set</a></aside><main class="main"><header class="head"><h1 style="margin:0">TKE RAG Assistant</h1><button onclick="logout()">Sign out</button></header><div id="msgs" class="messages"></div><form class="composer" onsubmit="send(event)"><textarea id="q" rows="2" style="flex:1" placeholder="Ask a question..."></textarea><button>Send</button></form></main></section>
<script>
async function login(){const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})}); if(r.ok){document.getElementById('login').classList.add('hidden');app.classList.remove('hidden');health()}else e.textContent='Invalid credentials'}
async function logout(){await fetch('/api/logout',{method:'POST'});location.reload()}
function msg(c,t){const d=document.createElement('div');d.className='msg '+c;d.textContent=t;msgs.append(d);msgs.scrollTop=msgs.scrollHeight}
async function health(){const r=await fetch('/api/health');const j=await r.json();document.getElementById('health').textContent=`${j.document_count} indexed documents`}
async function send(ev){ev.preventDefault();const text=q.value.trim();if(!text)return;q.value='';msg('user',text);const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});const j=await r.json();if(!r.ok){msg('bot',j.detail||'Error');return}msg('bot',j.answer);sources.innerHTML=(j.sources||[]).map(s=>`<div class="source"><a href="${s.url}" target="_blank">${s.title}</a><br>${s.date} · ${s.column} · ${Number(s.score||0).toFixed(3)}</div>`).join('')}
</script></body></html>"""


def main() -> None:
    load_env(Path(os.getenv("ENV_FILE", "/opt/rag-challenge/.env")))
    docs = build_documents_from_questions_html(QUESTIONS_PATH.read_text(encoding="utf-8"))
    docs = merge_article_cache(docs, load_article_cache())
    RagHandler.docs = docs
    RagHandler.username = os.getenv("APP_USERNAME", "reviewer")
    RagHandler.password = os.getenv("APP_PASSWORD", "change-me")
    RagHandler.secret = os.getenv("SESSION_SECRET", "dev-secret")
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Serving {len(docs)} local RAG documents on {host}:{port}")
    ThreadingHTTPServer((host, port), RagHandler).serve_forever()


if __name__ == "__main__":
    main()
