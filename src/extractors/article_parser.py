from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from utils.request_handler import RequestHandler, RequestError

def _extract_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """
    Extract metadata from common HTML meta tags.
    """
    metadata: Dict[str, Any] = {
        "canonicalUrl": None,
        "title": None,
        "description": None,
        "image": None,
        "source": None,
        "author": None,
        "keywords": None,
        "published": None,
        "languageCode": None,
    }

    # Canonical URL
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        metadata["canonicalUrl"] = canonical["href"]
    else:
        metadata["canonicalUrl"] = url

    # Title
    if soup.title and soup.title.string:
        metadata["title"] = soup.title.string.strip()

    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "title"})
    if og_title and og_title.get("content"):
        metadata["title"] = og_title["content"].strip()

    # Description
    desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta",
        property="og:description",
    )
    if desc and desc.get("content"):
        metadata["description"] = desc["content"].strip()

    # Image
    image_tag = soup.find("meta", property="og:image")
    if image_tag and image_tag.get("content"):
        metadata["image"] = image_tag["content"].strip()

    # Source / publisher
    source = soup.find("meta", attrs={"property": "og:site_name"}) or soup.find(
        "meta",
        attrs={"name": "publisher"},
    )
    if source and source.get("content"):
        metadata["source"] = source["content"].strip()

    # Author
    author = (
        soup.find("meta", attrs={"name": "author"})
        or soup.find("meta", property="article:author")
        or soup.find("span", attrs={"class": lambda c: c and "author" in c.lower()})
    )
    if author is not None:
        if author.name == "meta" and author.get("content"):
            metadata["author"] = author["content"].strip()
        elif author.string:
            metadata["author"] = author.string.strip()

    # Keywords
    keywords = soup.find("meta", attrs={"name": "keywords"})
    if keywords and keywords.get("content"):
        metadata["keywords"] = keywords["content"].strip()

    # Published date (common meta tags)
    published_meta = (
        soup.find("meta", property="article:published_time")
        or soup.find("meta", attrs={"name": "pubdate"})
        or soup.find("meta", attrs={"name": "date"})
    )
    if published_meta and published_meta.get("content"):
        metadata["published"] = published_meta["content"].strip()

    # Language code
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        metadata["languageCode"] = html_tag["lang"].strip()

    return metadata

def _extract_text(soup: BeautifulSoup) -> str:
    """
    Extract article text from the page.

    Preference order:
    1. <article> tag
    2. Main content containers
    3. All <p> elements
    """
    article_tag = soup.find("article")
    paragraphs = []

    if article_tag:
        paragraphs = article_tag.find_all("p")
    else:
        # Try common content containers
        main_candidates = soup.select("main, div[id*=content], div[class*=content]")
        for candidate in main_candidates:
            paragraphs = candidate.find_all("p")
            if paragraphs:
                break

    if not paragraphs:
        paragraphs = soup.find_all("p")

    texts = []
    for p in paragraphs:
        text = p.get_text(" ", strip=True)
        if len(text) < 40:
            continue
        texts.append(text)

    return "\n".join(texts).strip()

def parse_article(
    url: str,
    *,
    request_handler: RequestHandler,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch and parse a news article into a structured dictionary.

    Returns a dict with:
    - url
    - crawl: { loadedUrl, loadedTime, httpStatusCode }
    - metadata: {...}
    - title
    - text
    """
    logging.info("Fetching article at %s", url)

    try:
        response = request_handler.get(url, timeout=timeout)
    except RequestError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RequestError(f"Unexpected error fetching article: {exc}") from exc

    loaded_time = datetime.utcnow().isoformat() + "Z"
    status_code = response.status_code

    soup = BeautifulSoup(response.text, "html.parser")

    metadata = _extract_metadata(soup, url)
    text = _extract_text(soup)

    title = metadata.get("title")
    if not title:
        # Fallback to the first line of the article text
        first_line = text.split("\n", 1)[0] if text else ""
        title = first_line[:120] if first_line else url

    article = {
        "url": url,
        "crawl": {
            "loadedUrl": str(response.url),
            "loadedTime": loaded_time,
            "httpStatusCode": status_code,
        },
        "metadata": metadata,
        "title": title,
        "text": text,
    }

    logging.debug("Parsed article metadata for %s: %s", url, metadata)
    return article