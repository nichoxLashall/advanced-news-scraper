from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

class RequestError(RuntimeError):
    """Raised when HTTP requests repeatedly fail."""

class RequestHandler:
    """
    Simple HTTP client wrapper providing:
    - User-Agent configuration
    - Retry with exponential backoff
    - Basic logging
    """

    def __init__(
        self,
        *,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        user_agent: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self.session = requests.Session()
        headers = {
            "User-Agent": user_agent or "AdvancedNewsScraper/1.0 (+https://bitbash.dev)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.session.headers.update(headers)

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """
        Perform a GET request with retries and basic error handling.
        """
        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= self.max_retries:
            attempt += 1
            try:
                logging.debug("HTTP GET %s (attempt %d)", url, attempt)
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout or self.timeout,
                    allow_redirects=True,
                )
                if 200 <= response.status_code < 400:
                    return response

                logging.warning(
                    "Received non-success status code %s for %s",
                    response.status_code,
                    response.url,
                )
                last_exc = RequestError(f"HTTP {response.status_code} for {response.url}")
            except requests.RequestException as exc:
                logging.warning("Request error for %s: %s", url, exc)
                last_exc = exc

            if attempt <= self.max_retries:
                sleep_for = self.backoff_factor * (2 ** (attempt - 1))
                logging.debug("Retrying in %.2f seconds...", sleep_for)
                time.sleep(sleep_for)

        raise RequestError(f"Failed to fetch {url!r} after {self.max_retries} retries: {last_exc}")