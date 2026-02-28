"""URL → Markdown converter using trafilatura for article content extraction.

Handles news articles, blog posts, academic pages, Wikipedia, etc.
Strips navigation, ads, and boilerplate automatically.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Simple check: is this URL a YouTube video?
_YT_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)"
)


def is_youtube_url(url: str) -> bool:
    """Return True if the URL points to a YouTube video."""
    return bool(_YT_RE.search(url))


def convert_url(url: str) -> str:
    """Download a web page and extract its main article content as Markdown.

    Uses ``trafilatura`` for content extraction, which handles ads, sidebars,
    navigation, and most paywalls automatically.

    Falls back to BeautifulSoup if trafilatura is unavailable.

    Parameters
    ----------
    url:
        Fully-qualified URL (https://...).
    """
    # Normalise URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        import trafilatura
    except ImportError:
        return _fallback_scrape(url)

    logger.info("Fetching URL via trafilatura: %s", url)
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not download content from: {url}")

    # Extract structured metadata
    try:
        metadata = trafilatura.extract_metadata(downloaded)
    except Exception:
        metadata = None

    title = (metadata.title if metadata and metadata.title else None) or _url_title(url)
    author = metadata.author if metadata and metadata.author else None
    date = metadata.date if metadata and metadata.date else None
    description = metadata.description if metadata and metadata.description else None

    # Extract main article body as Markdown
    content = trafilatura.extract(
        downloaded,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_recall=True,
    )

    if not content:
        # trafilatura found nothing — fall back
        logger.warning("trafilatura extracted no content from %s, falling back", url)
        return _fallback_scrape(url)

    # Build Markdown document
    parts: list[str] = [f"# {title}", ""]

    meta_parts: list[str] = []
    if author:
        meta_parts.append(f"Author: {author}")
    if date:
        meta_parts.append(f"Date: {date}")
    meta_parts.append(f"Source: [{urlparse(url).netloc}]({url})")

    parts.append("*" + " · ".join(meta_parts) + "*")
    parts.append("")

    if description:
        parts.append(f"> {description}")
        parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(content)

    return "\n".join(parts)


def _url_title(url: str) -> str:
    """Derive a readable title from a URL when no metadata is available."""
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else urlparse(url).netloc
    return slug.replace("-", " ").replace("_", " ").title() or "Web Article"


def _fallback_scrape(url: str) -> str:
    """Minimal fallback scraper using requests + BeautifulSoup."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError(
            "URL import requires trafilatura or (requests + beautifulsoup4). "
            "Install with: pip install trafilatura"
        )

    logger.info("Falling back to requests/BeautifulSoup for %s", url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; PPKE/2.0; +https://github.com/ppke)"
        )
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else _url_title(url)
    text = soup.get_text(separator="\n").strip()
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return f"# {title}\n\n*Source: [{urlparse(url).netloc}]({url})*\n\n---\n\n{text}"
