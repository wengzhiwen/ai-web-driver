"""Merge annotated pages into Site Profile documents."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .models import AliasDefinition, AnnotatedPage, ProfileMergeResult


def _now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _alias_map(aliases: list[AliasDefinition]) -> Dict[str, dict]:
    payload: Dict[str, dict] = {}
    for alias in aliases:
        payload[alias.name] = alias.to_profile_dict()
    return payload


def _build_page_entry(page: AnnotatedPage) -> Dict[str, object]:
    timestamp = _now_ts()
    entry: Dict[str, object] = {
        "id": page.page_id,
        "name": page.page_name,
        "url_pattern": page.url_pattern,
        "version": timestamp,
        "generated_at": timestamp,
        "generated_by": "profile_builder_cli",
        "aliases": _alias_map(page.aliases),
    }
    if page.summary:
        entry["summary"] = page.summary
    return entry


def merge_page_into_profile(
    annotated_page: AnnotatedPage,
    *,
    output_path: Path,
    site_name: Optional[str] = None,
    dry_run: bool = False,
) -> ProfileMergeResult:
    """Merge annotated page into site profile file."""

    if output_path.exists():
        profile = json.loads(output_path.read_text(encoding="utf-8"))
        created_new = False
    else:
        profile = {
            "version": _now_ts(),
            "pages": [],
        }
        created_new = True
    if "pages" not in profile or not isinstance(profile["pages"], list):
        profile["pages"] = []

    if site_name:
        site_section = profile.setdefault("site", {})
        if isinstance(site_section, dict):
            site_section.setdefault("name", site_name)

    new_entry = _build_page_entry(annotated_page)

    existing = None
    for page in profile["pages"]:
        if isinstance(page, dict) and page.get("id") == annotated_page.page_id:
            existing = page
            break

    if existing is None:
        profile["pages"].append(new_entry)
    else:
        history = existing.setdefault("history", [])
        if isinstance(history, list):
            snapshot = {k: copy.deepcopy(v) for k, v in existing.items() if k != "history"}
            history.append(snapshot)
        existing.clear()
        existing.update(new_entry)
        if history:
            existing["history"] = history

    profile["version"] = _now_ts()

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    return ProfileMergeResult(
        output_path=output_path,
        created_new_file=created_new,
        page_id=annotated_page.page_id,
        warnings=list(annotated_page.warnings),
    )
