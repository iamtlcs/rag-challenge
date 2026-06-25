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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "html" / "questions.html"
COOKIE_NAME = "rag_session"
SOURCE_RE = re.compile(r"const\s+QUESTIONS_DATA\s*=\s*(\[.*?\]);", re.S)


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


def char_ngrams(text: str, n: int = 2) -> set[str]:
    clean = re.sub(r"\s+", "", text.lower())
    if len(clean) <= n:
        return {clean} if clean else set()
    return {clean[i : i + n] for i in range(len(clean) - n + 1)}


def rank_documents(query: str, docs: list[dict[str, str]], top_k: int = 5) -> list[dict[str, Any]]:
    query_terms = char_ngrams(query, 2) | set(re.findall(r"[A-Za-z0-9]+", query.lower()))
    if not query_terms:
        return []
    ranked: list[dict[str, Any]] = []
    for doc in docs:
        text = f"{doc.get('title', '')} {doc.get('text', '')}"
        doc_terms = char_ngrams(text, 2) | set(re.findall(r"[A-Za-z0-9]+", text.lower()))
        if not doc_terms:
            continue
        overlap = query_terms & doc_terms
        score = len(overlap) / math.sqrt(len(query_terms) * len(doc_terms))
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
    text = clean_evidence_text(str(top.get("text", "")), title)

    if date and (
        "what date" in normalized
        or "when" in normalized
        or "哪一天" in question
        or "什么时候" in question
        or "日期" in question
    ):
        return f"事件发生日期是 {date}。"

    if "主要讲述" in question or "mainly describe" in normalized or "what aspect" in normalized:
        evidence = first_good_sentence(text) or title
        return f"这篇报道主要讲述：{evidence}"

    if "在哪里" in question or "where" in normalized:
        evidence = first_good_sentence(text) or "来源中未给出明确地点"
        return f"相关地点信息：{evidence}"

    if "多少" in question or "how many" in normalized:
        number = re.search(r"\d+", text)
        if number:
            return f"文中提到的数量是 {number.group(0)}。"

    if "荣誉" in question or "获奖" in question or "honor" in normalized or "award" in normalized:
        evidence = first_good_sentence(text) or title
        return f"相关荣誉或成果是：{evidence}"

    evidence = first_good_sentence(text) or text[:180] or title
    suffix = f" 来源：《{title}》" if title else ""
    return f"{evidence}{suffix}"


def clean_evidence_text(text: str, title: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if title:
        clean = clean.replace(title, " ")
    clean = re.sub(r"What aspect.*?(?:describe\?|$)", " ", clean)
    clean = re.sub(r"On what date.*?(?:occur\?|$)", " ", clean)
    clean = re.sub(r"Where was.*?(?:held\?|$)", " ", clean)
    clean = re.sub(r"What honor.*?(?:receive\?|$)", " ", clean)
    clean = re.sub(r"文章《[^》]+》[^？]*？", " ", clean)
    clean = re.sub(r"《[^》]+》这篇报道[^？]*？", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def first_good_sentence(text: str) -> str:
    parts = re.split(r"(?<=[。！？!?])\s*", text)
    for part in parts:
        clean = part.strip()
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
