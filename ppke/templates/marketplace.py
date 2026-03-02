"""Plugin marketplace for discovering, sharing, and installing plugins.

Provides a JSON-backed marketplace catalog that supports listing, searching,
rating, and submitting plugins.  The catalog is stored at
``~/.ppke/marketplace.json`` alongside the existing plugin registry.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MARKETPLACE_FILE = Path.home() / ".ppke" / "marketplace.json"

# ── Seed catalog ────────────────────────────────────────────────────

_SEED_PLUGINS: List[Dict[str, Any]] = [
    {
        "name": "philosophy",
        "version": "2.0.0",
        "author": "PPKE Core Team",
        "description": "Philosophical text analysis with argument mapping, logical structure extraction, and concept indexing.",
        "tier": "official",
        "category": "humanities",
        "tags": ["philosophy", "argument-mapping", "logic", "ethics"],
        "downloads": 1250,
        "ratings": [5, 4, 5, 5, 4, 5],
        "source": "bundled",
        "created_at": "2025-06-01T00:00:00",
        "updated_at": "2026-01-15T00:00:00",
    },
    {
        "name": "legal",
        "version": "2.0.0",
        "author": "PPKE Core Team",
        "description": "Legal document analysis with case law references, statutory citations, and legal standard identification.",
        "tier": "official",
        "category": "professional",
        "tags": ["legal", "contracts", "case-law", "compliance"],
        "downloads": 980,
        "ratings": [5, 4, 4, 5, 5],
        "source": "bundled",
        "created_at": "2025-06-01T00:00:00",
        "updated_at": "2026-01-15T00:00:00",
    },
    {
        "name": "scientific_research",
        "version": "1.0.0",
        "author": "PPKE Core Team",
        "description": "Scientific paper analysis with methodology extraction, hypothesis tracking, and citation mapping.",
        "tier": "official",
        "category": "science",
        "tags": ["science", "research", "papers", "methodology", "citations"],
        "downloads": 720,
        "ratings": [4, 5, 4, 4, 5],
        "source": "bundled",
        "created_at": "2025-08-15T00:00:00",
        "updated_at": "2026-01-10T00:00:00",
    },
    {
        "name": "literary_analysis",
        "version": "1.0.0",
        "author": "Community",
        "description": "Fiction and literary text analysis with character mapping, theme extraction, and narrative structure.",
        "tier": "community",
        "category": "humanities",
        "tags": ["literature", "fiction", "characters", "themes", "narrative"],
        "downloads": 340,
        "ratings": [4, 3, 4, 5],
        "source": "community",
        "created_at": "2025-10-01T00:00:00",
        "updated_at": "2025-12-20T00:00:00",
    },
    {
        "name": "medical_notes",
        "version": "1.0.0",
        "author": "Community",
        "description": "Medical and clinical document analysis with diagnosis extraction, treatment plans, and terminology mapping.",
        "tier": "community",
        "category": "professional",
        "tags": ["medical", "clinical", "health", "diagnosis"],
        "downloads": 210,
        "ratings": [5, 4, 4],
        "source": "community",
        "created_at": "2025-11-01T00:00:00",
        "updated_at": "2026-01-05T00:00:00",
    },
    {
        "name": "business_strategy",
        "version": "1.0.0",
        "author": "Community",
        "description": "Business and strategy document analysis with SWOT extraction, competitive analysis, and KPI identification.",
        "tier": "community",
        "category": "professional",
        "tags": ["business", "strategy", "analysis", "management"],
        "downloads": 180,
        "ratings": [4, 3, 5],
        "source": "community",
        "created_at": "2025-12-01T00:00:00",
        "updated_at": "2026-02-01T00:00:00",
    },
]


def _default_catalog() -> Dict[str, Any]:
    """Return a fresh catalog seeded with official + sample community plugins."""
    return {
        "plugins": {p["name"]: dict(p) for p in _SEED_PLUGINS},
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def get_catalog() -> Dict[str, Any]:
    """Load the marketplace catalog from disk (or return the seed catalog)."""
    if not MARKETPLACE_FILE.exists():
        return _default_catalog()
    try:
        with open(MARKETPLACE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if not data.get("plugins"):
                return _default_catalog()
            return data
    except (json.JSONDecodeError, IOError):
        return _default_catalog()


def _save_catalog(catalog: Dict[str, Any]) -> None:
    """Persist the catalog to disk."""
    MARKETPLACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    catalog["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(MARKETPLACE_FILE, "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=2)


# ── Public helpers ──────────────────────────────────────────────────


def _avg_rating(ratings: List[int]) -> float:
    """Return the average rating rounded to one decimal place, or 0.0."""
    if not ratings:
        return 0.0
    return round(sum(ratings) / len(ratings), 1)


def _enrich(plugin: Dict[str, Any]) -> Dict[str, Any]:
    """Add computed fields (``average_rating``, ``rating_count``)."""
    enriched = dict(plugin)
    ratings = enriched.get("ratings", [])
    enriched["average_rating"] = _avg_rating(ratings)
    enriched["rating_count"] = len(ratings)
    return enriched


def list_marketplace_plugins(
    *,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "downloads",
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    """Return a paginated, filterable list of marketplace plugins.

    Parameters
    ----------
    category:
        Filter by category (e.g. ``"humanities"``, ``"science"``).
    search:
        Free-text search over name, description, tags.
    sort_by:
        One of ``"downloads"``, ``"rating"``, ``"name"``, ``"updated"``.
    page / per_page:
        Pagination controls.

    Returns
    -------
    dict with ``plugins``, ``total``, ``page``, ``total_pages``, ``categories``.
    """
    catalog = get_catalog()
    plugins = [_enrich(p) for p in catalog["plugins"].values()]

    # Collect unique categories before filtering
    all_categories = sorted({p.get("category", "other") for p in plugins})

    # ── Filter ──
    if category:
        plugins = [p for p in plugins if p.get("category") == category]

    if search:
        q = search.lower()
        plugins = [
            p for p in plugins
            if q in p["name"].lower()
            or q in p.get("description", "").lower()
            or any(q in tag for tag in p.get("tags", []))
        ]

    # ── Sort ──
    sort_keys = {
        "downloads": lambda p: p.get("downloads", 0),
        "rating": lambda p: p.get("average_rating", 0),
        "name": lambda p: p["name"],
        "updated": lambda p: p.get("updated_at", ""),
    }
    key_fn = sort_keys.get(sort_by, sort_keys["downloads"])
    reverse = sort_by != "name"
    plugins.sort(key=key_fn, reverse=reverse)

    # ── Paginate ──
    total = len(plugins)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_plugins = plugins[start : start + per_page]

    return {
        "plugins": page_plugins,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": all_categories,
    }


def get_marketplace_plugin(name: str) -> Optional[Dict[str, Any]]:
    """Return enriched detail for a single marketplace plugin, or ``None``."""
    catalog = get_catalog()
    plugin = catalog["plugins"].get(name)
    if plugin is None:
        return None
    return _enrich(plugin)


def rate_plugin(name: str, rating: int) -> Optional[Dict[str, Any]]:
    """Add a rating (1-5) to a marketplace plugin.

    Returns the updated plugin dict, or ``None`` if not found.
    """
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")

    catalog = get_catalog()
    if name not in catalog["plugins"]:
        return None

    catalog["plugins"][name].setdefault("ratings", []).append(rating)
    _save_catalog(catalog)
    return _enrich(catalog["plugins"][name])


def submit_plugin(
    name: str,
    version: str,
    author: str,
    description: str,
    category: str = "other",
    tags: Optional[List[str]] = None,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit a new plugin to the marketplace catalog.

    Raises ``ValueError`` if *name* already exists.
    """
    catalog = get_catalog()
    if name in catalog["plugins"]:
        raise ValueError(f"Plugin '{name}' already exists in the marketplace")

    plugin: Dict[str, Any] = {
        "name": name,
        "version": version,
        "author": author,
        "description": description,
        "tier": "community",
        "category": category,
        "tags": tags or [],
        "downloads": 0,
        "ratings": [],
        "source": f"github:{source_url}" if source_url else "community",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    catalog["plugins"][name] = plugin
    _save_catalog(catalog)
    return _enrich(plugin)


def increment_downloads(name: str) -> None:
    """Bump the download counter for *name* (no-op if not found)."""
    catalog = get_catalog()
    if name in catalog["plugins"]:
        catalog["plugins"][name]["downloads"] = (
            catalog["plugins"][name].get("downloads", 0) + 1
        )
        _save_catalog(catalog)
