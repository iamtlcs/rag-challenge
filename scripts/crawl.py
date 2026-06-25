from __future__ import annotations

import argparse
from pathlib import Path

from app.crawler import crawl_urls, extract_question_seed_urls, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl the Tsinghua School of Software corpus.")
    parser.add_argument("--seeds-from", type=Path, default=Path("html/questions.html"))
    parser.add_argument("--out", type=Path, default=Path("data/corpus.jsonl"))
    parser.add_argument("--max-pages", type=int, default=900)
    parser.add_argument("--delay", type=float, default=0.75)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_html = args.seeds_from.read_text(encoding="utf-8")
    seeds = extract_question_seed_urls(seed_html)
    records = crawl_urls(seeds, max_pages=args.max_pages, delay=args.delay)
    write_jsonl(records, args.out)
    print(f"Wrote {len(records)} records to {args.out}")


if __name__ == "__main__":
    main()
