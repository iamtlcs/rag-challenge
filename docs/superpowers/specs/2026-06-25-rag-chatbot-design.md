# RAG Chatbot Deployment Design

## Goal

Build and deploy an authenticated RAG chatbot for the TKE challenge on the provided server, replacing the public root with the chatbot while preserving the original challenge pages under `/challenge/`.

## Recommended Approach

Use a compact Python FastAPI application. It is the best fit for the target Ubuntu server because the brief says Python 3.10 is available, it avoids a JavaScript build step, and it keeps crawler, indexer, API, and deployment in one repo.

Alternatives considered:

- Full JavaScript app: good UI tooling, but adds a larger runtime and build pipeline.
- Heavy vector database stack: better for very large corpora, but unnecessary for about 850 pages and risky under the time limit.

## Components

- Crawler: starts from the known evaluation source URLs embedded in `html/questions.html`, follows same-site article/list links, respects robots where present, uses a clear User-Agent, and sleeps between requests.
- Corpus store: JSONL records with URL, title, date, column, body text, image URLs, and crawl timestamp. The raw corpus is generated on the server and ignored by git.
- Indexer: chunks article bodies and builds a scikit-learn character n-gram TF-IDF index. Character n-grams work well for mixed Chinese and English without a separate tokenizer.
- Retriever: ranks chunks by cosine similarity and returns source metadata with scores.
- Answerer: uses OpenAI-compatible generation if `OPENAI_API_KEY` is configured. Otherwise it creates an extractive answer from top chunks so the deployed app remains functional without external secrets.
- Web app: FastAPI session cookie authentication, static login/chat UI, `/api/chat`, `/api/health`, and static `/challenge/` pages.
- Deployment: systemd runs Uvicorn on localhost; Nginx terminates HTTPS on `8443` and reverse proxies to the app.

## Data Flow

1. `scripts.crawl` fetches article pages and writes `data/corpus.jsonl`.
2. `scripts.build_index` chunks corpus records and writes `data/index`.
3. FastAPI loads the index at startup.
4. Authenticated chat requests retrieve relevant chunks.
5. The answerer returns an answer plus source citations.

## Error Handling

- Missing index returns a clear 503 with setup guidance.
- Empty retrieval returns a graceful "not enough evidence" answer.
- Crawler records failed URLs in logs and continues.
- Authentication failures return generic errors without revealing which field was wrong.

## Testing

Unit tests cover:

- Article extraction and chunking.
- TF-IDF retrieval ranking and citation metadata.
- Answer fallback behavior.
- Login cookie creation and protected API access.

Smoke tests cover app startup and `/api/health`.
