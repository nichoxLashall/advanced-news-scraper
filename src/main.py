import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Ensure local imports work when running as a script
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from extractors.article_parser import parse_article  # type: ignore
from extractors.ai_summarizer import summarize  # type: ignore
from utils.request_handler import RequestHandler, RequestError  # type: ignore
from utils.data_formatter import build_article_record, write_json  # type: ignore

def load_settings_example() -> Dict[str, Any]:
    """
    Load settings from src/config/settings.example.json.
    These act as sensible defaults and the scraper will run
    even if this file is missing by falling back to hard-coded values.
    """
    default_settings: Dict[str, Any] = {
        "default_query": "artificial intelligence",
        "region": "us-en",
        "language": "en",
        "max_articles": 10,
        "hours_back": 24,
        "request_timeout": 10,
        "user_agent": "AdvancedNewsScraper/1.0 (+https://bitbash.dev)",
    }

    config_path = os.path.join(CURRENT_DIR, "config", "settings.example.json")
    if not os.path.exists(config_path):
        logging.warning("settings.example.json not found, using built-in defaults.")
        return default_settings

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            file_settings = json.load(f)
        merged = {**default_settings, **file_settings}
        return merged
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to load settings.example.json: %s", exc)
        return default_settings

def load_input_file(path: str) -> List[Dict[str, Any]]:
    """
    Load input configuration from JSON.

    Expected shape:
    {
      "queries": [
        {
          "query": "openai board women in tech",
          "region": "us-en",
          "language": "en",
          "max_articles": 5,
          "hours_back": 48
        }
      ]
    }
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    queries = payload.get("queries")
    if not isinstance(queries, list):
        raise ValueError("Input file must contain a 'queries' array.")

    normalized: List[Dict[str, Any]] = []
    for item in queries:
        if not isinstance(item, dict) or "query" not in item:
            raise ValueError("Each entry in 'queries' must be an object with at least a 'query' field.")
        normalized.append(item)
    return normalized

def search_news_duckduckgo(
    query: str,
    *,
    max_articles: int,
    region: Optional[str],
    language: Optional[str],
    request_handler: RequestHandler,
) -> List[str]:
    """
    Perform a lightweight DuckDuckGo HTML search and return article URLs.

    This avoids API keys and keeps the project self-contained.
    """
    from bs4 import BeautifulSoup  # imported here to keep dependencies localized

    search_url = "https://duckduckgo.com/html/"
    params = {
        "q": query,
    }
    if region:
        params["kl"] = region

    logging.info("Searching DuckDuckGo for query='%s' region='%s'", query, region or "default")

    try:
        response = request_handler.get(search_url, params=params)
    except RequestError as exc:
        logging.error("Search request failed: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    urls: List[str] = []

    # DuckDuckGo's result links typically have class 'result__a' but may vary.
    # We keep this resilient by also falling back to generic result containers.
    for link in soup.select("a.result__a"):
        href = link.get("href")
        if not href:
            continue
        if href.startswith("http"):
            urls.append(href)
        if len(urls) >= max_articles:
            break

    if not urls:
        # Fallback: scan generic links in result snippets
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.startswith("http"):
                urls.append(href)
            if len(urls) >= max_articles:
                break

    logging.info("Found %d candidate article URLs", len(urls))
    return urls[:max_articles]

def parse_iso8601(value: str) -> Optional[datetime]:
    """
    Best-effort ISO-8601 parsing for published timestamps.
    Returns None if parsing fails.
    """
    if not value:
        return None

    # Normalize common suffixes
    cleaned = value.strip()
    cleaned = cleaned.replace("Z", "+00:00")
    # Try a couple of simple patterns
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None

def filter_by_freshness(
    records: List[Dict[str, Any]],
    *,
    max_age_hours: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Filter records by their metadata.published timestamp if max_age_hours is provided.
    """
    if not max_age_hours:
        return records

    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    filtered: List[Dict[str, Any]] = []

    for rec in records:
        published_raw = None
        try:
            published_raw = rec.get("metadata", {}).get("published")
        except Exception:
            published_raw = None

        if not published_raw:
            # If unknown, keep the article; freshness is best-effort.
            filtered.append(rec)
            continue

        dt = parse_iso8601(published_raw)
        if dt is None or dt >= cutoff:
            filtered.append(rec)

    logging.info(
        "Filtered %d records to %d using freshness window of %s hours",
        len(records),
        len(filtered),
        max_age_hours,
    )
    return filtered

def run_scraper(args: argparse.Namespace) -> None:
    settings = load_settings_example()

    request_handler = RequestHandler(
        timeout=settings.get("request_timeout", 10),
        max_retries=3,
        backoff_factor=0.5,
        user_agent=settings.get("user_agent"),
    )

    if args.input:
        queries = load_input_file(args.input)
    else:
        query_text = args.query or settings.get("default_query")
        if not query_text:
            raise ValueError("No query provided and no default_query configured.")
        queries = [
            {
                "query": query_text,
                "region": settings.get("region"),
                "language": settings.get("language"),
                "max_articles": args.max_articles or settings.get("max_articles", 10),
                "hours_back": args.since_hours or settings.get("hours_back"),
            }
        ]

    all_records: List[Dict[str, Any]] = []

    for q in queries:
        query_text = q.get("query", "")
        region = q.get("region", settings.get("region"))
        language = q.get("language", settings.get("language"))
        max_articles = int(q.get("max_articles", settings.get("max_articles", 10)))
        hours_back = q.get("hours_back", settings.get("hours_back"))

        logging.info(
            "Processing query='%s' region='%s' language='%s' max_articles=%d hours_back=%s",
            query_text,
            region,
            language,
            max_articles,
            hours_back,
        )

        urls = search_news_duckduckgo(
            query_text,
            max_articles=max_articles,
            region=region,
            language=language,
            request_handler=request_handler,
        )

        for url in urls:
            try:
                article = parse_article(url, request_handler=request_handler)
            except RequestError as exc:
                logging.warning("Skipping URL due to request error: %s (url=%s)", exc, url)
                continue
            except Exception as exc:  # noqa: BLE001
                logging.exception("Unexpected error parsing article at %s: %s", url, exc)
                continue

            ai_summary = summarize(
                text=article.get("text", "") or "",
                query=query_text,
                metadata_title=article.get("title"),
            )

            record = build_article_record(
                url=url,
                crawl_info=article.get("crawl", {}),
                metadata=article.get("metadata", {}),
                ai_summary=ai_summary,
                full_text=article.get("text", "") or "",
                display_title=article.get("title") or ai_summary.get("title") or "",
            )
            all_records.append(record)

        all_records = filter_by_freshness(all_records, max_age_hours=hours_back)

    write_json(all_records, output_path=args.output, pretty=True)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Advanced News Scraper - fetch, summarize, and format news articles.",
    )
    parser.add_argument(
        "-q",
        "--query",
        help="Search query text (ignored if --input is provided).",
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Path to JSON file containing an array of query definitions.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write JSON output (defaults to stdout if omitted).",
    )
    parser.add_argument(
        "-m",
        "--max-articles",
        type=int,
        help="Maximum number of articles to fetch per query.",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        help="Only keep articles published within the last N hours (best-effort).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        run_scraper(args)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fatal error running scraper: %s", exc)
        sys.exit(1)

if __name__ == "__main__":
    main()