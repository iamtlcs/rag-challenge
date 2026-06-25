# RAG Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy an authenticated RAG chatbot for the TKE challenge.

**Architecture:** FastAPI serves a static authenticated chat UI and API. A polite crawler builds a JSONL corpus, an indexer creates a TF-IDF chunk index, and the runtime answers from retrieved chunks with citations.

**Tech Stack:** Python 3.10, FastAPI, BeautifulSoup, scikit-learn, joblib, optional OpenAI SDK, Nginx, systemd.

---

### Task 1: Repository Skeleton

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `LICENSE`
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `data/.gitkeep`
- Create: `docs/superpowers/specs/2026-06-25-rag-chatbot-design.md`

- [x] Add project docs, dependency pins, config template, and ignore generated data.
- [x] Commit as `docs: add rag implementation design`.

### Task 2: Retrieval and Answer Tests

**Files:**
- Create: `tests/test_text.py`
- Create: `tests/test_retrieval.py`
- Create: `tests/test_answerer.py`

- [ ] Write tests for sentence splitting, chunking, TF-IDF retrieval, and extractive answers.
- [ ] Run `pytest tests/test_text.py tests/test_retrieval.py tests/test_answerer.py -q` and confirm failures before production code.
- [ ] Implement `app/rag/text.py`, `app/rag/indexing.py`, `app/rag/retriever.py`, and `app/rag/answerer.py`.
- [ ] Run tests and commit as `feat: add rag retrieval pipeline`.

### Task 3: Crawler Tests and Implementation

**Files:**
- Create: `tests/test_crawler.py`
- Create: `app/crawler.py`
- Create: `scripts/crawl.py`
- Create: `scripts/build_index.py`

- [ ] Write tests for extracting question seed URLs and parsing article HTML.
- [ ] Run crawler tests and confirm failures.
- [ ] Implement crawler extraction, polite fetching, JSONL writing, and index build CLI.
- [ ] Run tests and commit as `feat: add corpus crawler and indexer`.

### Task 4: Authenticated Web App

**Files:**
- Create: `tests/test_app.py`
- Create: `app/main.py`
- Create: `app/settings.py`
- Create: `app/auth.py`
- Create: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`

- [ ] Write tests for login, protected chat API, health, and missing-index behavior.
- [ ] Run app tests and confirm failures.
- [ ] Implement FastAPI app, sessions, endpoints, and static UI.
- [ ] Run tests and commit as `feat: add authenticated chat app`.

### Task 5: Deployment

**Files:**
- Create: `deploy/rag-challenge.service`
- Create: `deploy/nginx-rag-challenge.conf`
- Create: `scripts/smoke_chat.py`

- [ ] Add systemd and Nginx templates.
- [ ] Run local tests and app smoke check.
- [ ] Commit as `chore: add deployment assets`.
- [ ] Package and upload to `/opt/rag-challenge`.
- [ ] Install dependencies, crawl, build index, start service, and verify `https://123.59.90.15:8443`.
