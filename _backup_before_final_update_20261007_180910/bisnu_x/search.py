from __future__ import annotations

import html
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from bisnu_x.config import settings


HEADERS = {
    "User-Agent":
        "BISNU-X/7.0 (+local-ai-search)"
}


def clean(text: str):
    text = html.unescape(text or "")
    text = re.sub(
        r"\s+",
        " ",
        text
    )
    return text.strip()


def search(
    query: str,
    limit: int | None = None
):
    if not settings.live_search_enabled:
        return []

    query = clean(query)

    if not query:
        return []

    limit = (
        limit
        or settings.search_results
    )

    url = (
        "https://html.duckduckgo.com/html/?q="
        + quote_plus(query)
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=12
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

    except requests.RequestException as exc:
        raise RuntimeError("Live search request failed.") from exc

    results = []

    for item in soup.select(
        ".result"
    ):

        link = item.select_one(
            ".result__a"
        )

        snippet = item.select_one(
            ".result__snippet"
        )

        if not link:
            continue

        title = clean(
            link.get_text(" ", strip=True)
        )

        href = link.get(
            "href",
            ""
        )

        description = clean(
            snippet.get_text(
                " ",
                strip=True
            )
            if snippet
            else ""
        )

        if not href:
            continue

        results.append(
            {
                "title": title,
                "url": href,
                "snippet": description
            }
        )

        if len(results) >= limit:
            break

    return results
