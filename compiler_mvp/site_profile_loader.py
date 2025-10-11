"""Loads simplified site profile information for the compiler."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .models import SiteAlias, SiteProfile


def load_site_profile(path: Path) -> SiteProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pages = raw.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Site profile must contain a 'pages' array")

    aliases: Dict[str, SiteAlias] = {}
    for page in pages:
        page_id = page.get("id") or page.get("pageId")
        if not page_id:
            raise ValueError("Each page must define an 'id'")
        page_aliases = page.get("aliases")
        if not isinstance(page_aliases, dict):
            continue
        for alias_name, alias_payload in page_aliases.items():
            selector = alias_payload.get("selector")
            if not selector:
                continue
            aliases[alias_name] = SiteAlias(
                name=alias_name,
                selector=selector,
                description=alias_payload.get("description"),
                page_id=page_id,
            )

    if not aliases:
        raise ValueError("Site profile does not contain usable aliases")

    return SiteProfile(aliases=aliases, raw=raw)
