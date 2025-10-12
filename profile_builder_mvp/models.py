"""Dataclasses for the profile builder CLI MVP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FetchOptions:
    """Options controlling the page fetch process."""

    wait_for: Optional[str] = None
    timeout_ms: int = 10_000
    include_screenshot: bool = False


@dataclass
class FetchedPage:
    """Snapshot of a fetched page."""

    url: str
    title: str
    html: str
    dom_summary: Dict[str, Any]
    fetched_at: datetime
    screenshot_path: Optional[Path] = None
    controls: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnnotationRequest:
    """Payload sent to the LLM annotator."""

    url: str
    title: str
    dom_summary: Dict[str, Any]
    site_name: Optional[str]
    base_url: Optional[str]
    model: Optional[str] = None
    temperature: float = 0.2
    is_detail_page: bool = False
    detail_label: Optional[str] = None


@dataclass
class AliasDefinition:
    """Single alias entry in the generated profile."""

    name: str
    selector: str
    description: Optional[str] = None
    role: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None

    def to_profile_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"selector": self.selector}
        if self.description:
            payload["description"] = self.description
        if self.role:
            payload["role"] = self.role
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.notes:
            payload["notes"] = self.notes
        return payload


@dataclass
class AnnotatedPage:
    """Result returned by the LLM annotator."""

    page_id: str
    page_name: str
    url_pattern: str
    summary: Optional[str]
    aliases: List[AliasDefinition] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dom_summary: Optional[Dict[str, Any]] = None


@dataclass
class ProfileMergeResult:
    """Outcome of merging generated page info into a profile."""

    output_path: Path
    created_new_file: bool
    page_id: str
    warnings: List[str] = field(default_factory=list)
