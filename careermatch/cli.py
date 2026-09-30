import argparse
import asyncio
import json
from pathlib import Path

from .api import ROOT
from .extraction import extract_instructor, extract_rules
from .matching import SemanticEmbedding, match
from .models import MatchRequest
from .scraping import BrowserCollector


def main():
    parser = argparse.ArgumentParser(description="CareerMatch: evidence-linked matching")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Match the bundled fictional candidate and jobs")
    demo.add_argument("--output", type=Path)
    matching = sub.add_parser("match", help="Match a JSON request (resume + jobs)")
    matching.add_argument("input", type=Path)
    matching.add_argument(
        "--semantic", action="store_true", help="Downloads optional embedding model"
    )
    matching.add_argument(
        "--llm", action="store_true", help="Send job text to configured OpenAI model"
    )
    matching.add_argument("--output", type=Path)
    scrape = sub.add_parser("scrape", help="Fetch explicitly permitted public job pages")
    scrape.add_argument("urls", nargs="+")
    scrape.add_argument("--allow-host", action="append", required=True)
    scrape.add_argument("--concurrency", type=int, default=4)
    scrape.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "scrape":
            result = asyncio.run(
                BrowserCollector(set(args.allow_host)).run(args.urls, args.concurrency)
            )
        else:
            source = ROOT / "fixtures" / "demo.json" if args.command == "demo" else args.input
            request = MatchRequest.model_validate_json(source.read_text(encoding="utf-8"))
            result = match(
                request,
                SemanticEmbedding() if getattr(args, "semantic", False) else None,
                extract_instructor if getattr(args, "llm", False) else extract_rules,
            )
        rendered = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved {args.output}")
        else:
            print(rendered)
        if args.command == "scrape" and result.errors:
            parser.exit(
                2, f"Collection completed with {len(result.errors)} failed URLs; see output.\n"
            )
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"CareerMatch failed: {exc}\n")


if __name__ == "__main__":
    main()
