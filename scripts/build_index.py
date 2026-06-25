from __future__ import annotations

import argparse
from pathlib import Path

from app.rag.indexing import build_index, read_jsonl, save_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the RAG search index.")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/index"))
    parser.add_argument("--chunk-chars", type=int, default=900)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.corpus)
    index = build_index(records, chunk_chars=args.chunk_chars)
    path = save_index(index, args.out)
    print(f"Indexed {len(index.chunks)} chunks from {len(records)} records into {path}")


if __name__ == "__main__":
    main()
