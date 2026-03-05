"""GitHub Pull Request → Markdown converter.

Fetches PR metadata, diff, review comments, and conversations via the
GitHub REST API and converts them into a structured Markdown document
suitable for ingestion under the ``gh_pr`` domain template.

Environment variables:
    GITHUB_TOKEN — Personal access token for authenticated requests
                   (higher rate limits, access to private repos).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Pattern to match GitHub PR URLs:  https://github.com/owner/repo/pull/123
_GH_PR_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


def is_github_pr_url(url: str) -> bool:
    """Return True if *url* looks like a GitHub pull request URL."""
    return bool(_GH_PR_RE.match(url.strip()))


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Extract (owner, repo, pr_number) from a GitHub PR URL.

    Raises ``ValueError`` for malformed URLs.
    """
    m = _GH_PR_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"Not a valid GitHub PR URL: {url!r}. "
            "Expected: https://github.com/owner/repo/pull/123"
        )
    return m.group("owner"), m.group("repo"), int(m.group("number"))


# ------------------------------------------------------------------
# GitHub API helpers
# ------------------------------------------------------------------

def _github_headers(token: str | None = None) -> dict[str, str]:
    """Build HTTP headers for GitHub API requests."""
    token = token or os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PPKE/3.0 (GitHub PR Ingestion)",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _github_get(endpoint: str, token: str | None = None) -> Any:
    """Perform a GET request to the GitHub REST API.

    Parameters
    ----------
    endpoint:
        Full URL or path relative to ``https://api.github.com``.
    token:
        Optional GitHub personal access token.

    Returns the parsed JSON response.

    Raises ``ValueError`` on HTTP errors.
    """
    import urllib.request
    import urllib.error
    import json

    if not endpoint.startswith("http"):
        endpoint = f"https://api.github.com{endpoint}"

    req = urllib.request.Request(endpoint, headers=_github_headers(token))

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code == 404:
            raise ValueError(
                f"GitHub PR not found (404). The repository may be private "
                f"or the PR number may be invalid. URL: {endpoint}"
            ) from exc
        if exc.code == 403:
            raise ValueError(
                f"GitHub API rate limit exceeded or access denied (403). "
                f"Set GITHUB_TOKEN environment variable for higher limits. "
                f"Response: {body[:200]}"
            ) from exc
        raise ValueError(
            f"GitHub API error {exc.code}: {body[:300]}"
        ) from exc


def _github_get_text(endpoint: str, token: str | None = None) -> str:
    """GET a text (non-JSON) resource from GitHub API."""
    import urllib.request
    import urllib.error

    if not endpoint.startswith("http"):
        endpoint = f"https://api.github.com{endpoint}"

    headers = _github_headers(token)
    headers["Accept"] = "application/vnd.github.v3.diff"

    req = urllib.request.Request(endpoint, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise ValueError(f"GitHub API error {exc.code}: {body[:300]}") from exc


# ------------------------------------------------------------------
# PR data fetching
# ------------------------------------------------------------------

def fetch_pr_data(
    owner: str,
    repo: str,
    pr_number: int,
    token: str | None = None,
    include_comments: bool = True,
    include_reviews: bool = True,
) -> dict[str, Any]:
    """Fetch all relevant data for a GitHub PR.

    Returns a dictionary with keys:
        - ``pr``: PR metadata (title, body, author, state, etc.)
        - ``diff``: The unified diff as a string
        - ``files``: List of changed files with stats
        - ``comments``: Issue comments (if *include_comments*)
        - ``reviews``: Review comments (if *include_reviews*)
    """
    base = f"/repos/{owner}/{repo}/pulls/{pr_number}"

    logger.info("Fetching PR #%d from %s/%s", pr_number, owner, repo)

    # Core PR metadata
    pr = _github_get(base, token)

    # Diff
    try:
        diff = _github_get_text(base, token)
    except Exception as exc:
        logger.warning("Could not fetch diff: %s", exc)
        diff = ""

    # Changed files
    try:
        files = _github_get(f"{base}/files", token)
    except Exception:
        files = []

    # Issue comments (conversation)
    comments: list[dict] = []
    if include_comments:
        try:
            comments = _github_get(
                f"/repos/{owner}/{repo}/issues/{pr_number}/comments", token
            )
        except Exception:
            pass

    # Review comments (inline code comments)
    reviews: list[dict] = []
    if include_reviews:
        try:
            reviews = _github_get(f"{base}/reviews", token)
        except Exception:
            pass

    return {
        "pr": pr,
        "diff": diff,
        "files": files if isinstance(files, list) else [],
        "comments": comments if isinstance(comments, list) else [],
        "reviews": reviews if isinstance(reviews, list) else [],
    }


# ------------------------------------------------------------------
# Markdown conversion
# ------------------------------------------------------------------

def _format_diff_section(diff: str, max_lines: int = 500) -> str:
    """Format a unified diff into a readable Markdown code block.

    Truncates very large diffs to *max_lines* lines.
    """
    lines = diff.splitlines()
    if len(lines) > max_lines:
        truncated = lines[:max_lines]
        truncated.append(f"... ({len(lines) - max_lines} more lines truncated)")
        diff = "\n".join(truncated)
    return f"```diff\n{diff}\n```"


def _format_files_table(files: list[dict]) -> str:
    """Build a Markdown table of changed files."""
    if not files:
        return "*No file changes detected.*"

    lines = [
        "| File | Status | Additions | Deletions |",
        "|------|--------|-----------|-----------|",
    ]
    for f in files:
        fname = f.get("filename", "unknown")
        status = f.get("status", "modified")
        adds = f.get("additions", 0)
        dels = f.get("deletions", 0)
        lines.append(f"| `{fname}` | {status} | +{adds} | -{dels} |")

    return "\n".join(lines)


def _format_comments(comments: list[dict]) -> str:
    """Format PR comments as Markdown sections."""
    if not comments:
        return "*No comments.*"

    parts: list[str] = []
    for c in comments:
        author = c.get("user", {}).get("login", "unknown")
        body = c.get("body", "").strip()
        created = c.get("created_at", "")[:10]
        parts.append(f"**@{author}** ({created}):\n\n{body}")

    return "\n\n---\n\n".join(parts)


def _format_reviews(reviews: list[dict]) -> str:
    """Format PR reviews as Markdown."""
    if not reviews:
        return "*No reviews.*"

    parts: list[str] = []
    for r in reviews:
        author = r.get("user", {}).get("login", "unknown")
        state = r.get("state", "COMMENTED")
        body = (r.get("body") or "").strip()
        submitted = (r.get("submitted_at") or "")[:10]

        state_emoji = {
            "APPROVED": "✅",
            "CHANGES_REQUESTED": "❌",
            "COMMENTED": "💬",
            "DISMISSED": "🔄",
        }.get(state, "📝")

        header = f"{state_emoji} **@{author}** — {state} ({submitted})"
        if body:
            parts.append(f"{header}\n\n{body}")
        else:
            parts.append(header)

    return "\n\n---\n\n".join(parts)


def convert_github_pr(
    url: str,
    token: str | None = None,
    include_comments: bool = True,
    include_reviews: bool = True,
) -> str:
    """Fetch a GitHub PR and convert it to a structured Markdown document.

    Parameters
    ----------
    url:
        GitHub PR URL (e.g., ``https://github.com/owner/repo/pull/123``).
    token:
        Optional GitHub personal access token.
    include_comments:
        Whether to include PR conversation comments.
    include_reviews:
        Whether to include code review comments.

    Returns a Markdown string ready for PPKE ingestion.
    """
    owner, repo, pr_number = parse_pr_url(url)
    data = fetch_pr_data(
        owner, repo, pr_number, token,
        include_comments=include_comments,
        include_reviews=include_reviews,
    )

    pr = data["pr"]
    title = pr.get("title", f"PR #{pr_number}")
    body = pr.get("body") or ""
    author = pr.get("user", {}).get("login", "unknown")
    state = pr.get("state", "unknown")
    created = (pr.get("created_at") or "")[:10]
    updated = (pr.get("updated_at") or "")[:10]
    base_branch = pr.get("base", {}).get("ref", "main")
    head_branch = pr.get("head", {}).get("ref", "unknown")
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    changed_files_count = pr.get("changed_files", 0)
    labels = [l.get("name", "") for l in (pr.get("labels") or [])]
    merged = pr.get("merged", False)

    # Build the Markdown document
    sections: list[str] = []

    # Title & metadata
    sections.append(f"# PR #{pr_number}: {title}")
    sections.append("")
    sections.append(f"*Repository: [{owner}/{repo}](https://github.com/{owner}/{repo})*")
    sections.append(f"*Author: @{author} · State: {state} · Created: {created} · Updated: {updated}*")
    if merged:
        sections.append("*Status: **Merged** ✅*")
    if labels:
        sections.append(f"*Labels: {', '.join(labels)}*")
    sections.append(f"*Branch: `{head_branch}` → `{base_branch}` · {changed_files_count} files changed (+{additions} −{deletions})*")
    sections.append("")

    # PR Description
    sections.append("## Description")
    sections.append("")
    if body.strip():
        sections.append(body)
    else:
        sections.append("*No description provided.*")
    sections.append("")

    # Changed files
    sections.append("## Changed Files")
    sections.append("")
    sections.append(_format_files_table(data["files"]))
    sections.append("")

    # Diff
    sections.append("## Code Changes (Diff)")
    sections.append("")
    if data["diff"]:
        sections.append(_format_diff_section(data["diff"]))
    else:
        sections.append("*Diff not available.*")
    sections.append("")

    # Reviews
    if include_reviews and data["reviews"]:
        sections.append("## Code Reviews")
        sections.append("")
        sections.append(_format_reviews(data["reviews"]))
        sections.append("")

    # Comments
    if include_comments and data["comments"]:
        sections.append("## Discussion")
        sections.append("")
        sections.append(_format_comments(data["comments"]))
        sections.append("")

    return "\n".join(sections)


def pr_metadata(url: str, token: str | None = None) -> dict[str, str]:
    """Return lightweight metadata dict for a PR (no diff, no comments).

    Useful for populating form fields before a full fetch.
    """
    owner, repo, pr_number = parse_pr_url(url)
    pr = _github_get(f"/repos/{owner}/{repo}/pulls/{pr_number}", token)
    return {
        "title": pr.get("title", f"PR #{pr_number}"),
        "author": pr.get("user", {}).get("login", "unknown"),
        "number": str(pr_number),
        "repo": f"{owner}/{repo}",
        "state": pr.get("state", "unknown"),
    }
