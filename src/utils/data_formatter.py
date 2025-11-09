from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

def build_article_record(
    *,
    url: str,
    crawl_info: Dict[str, Any],
    metadata: Dict[str, Any],
    ai_summary: Dict[str, Any],
    full_text: str,
    display_title: str,
) -> Dict[str, Any]:
    """
    Build the final record structure for a single article.

    The structure is intentionally aligned with the README specification.
    """
    record = {
        "url": url,
        "crawl": {
            "loadedUrl": crawl_info.get("loadedUrl"),
            "loadedTime": crawl_info.get("loadedTime"),
            "httpStatusCode": crawl_info.get("httpStatusCode"),
        },
        "aiSummary": {
            "title": ai_summary.get("title"),
            "summary": ai_summary.get("summary"),
            "score": ai_summary.get("score"),
        },
        "metadata": {
            "canonicalUrl": metadata.get("canonicalUrl"),
            "title": metadata.get("title"),
            "description": metadata.get("description"),
            "image": metadata.get("image"),
            "source": metadata.get("source"),
            "author": metadata.get("author"),
            "keywords": metadata.get("keywords"),
            "published": metadata.get("published"),
            "languageCode": metadata.get("languageCode"),
        },
        "title": display_title,
        "text": full_text,
    }
    return record

def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

def write_json(
    data: List[Dict[str, Any]],
    *,
    output_path: Optional[str],
    pretty: bool = True,
) -> None:
    """
    Write records to disk or stdout.

    If output_path is None, the JSON is printed to stdout.
    """
    if pretty:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    if output_path:
        _ensure_parent_dir(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(payload)
        logging.info("Wrote %d records to %s", len(data), output_path)
    else:
        print(payload)