"""Data structures used by the compiler MVP."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TestStep:
    """Represents a single natural-language test step."""

    index: int
    text: str


@dataclass
class TestRequest:
    """Parsed test request document."""

    title: str
    base_url: Optional[str]
    steps: List[TestStep]
    source_path: Path


@dataclass
class SiteAlias:
    """Alias definition within a SiteProfile."""

    name: str
    selector: str
    description: Optional[str]
    page_id: str


@dataclass
class SiteProfile:
    """Simplified site profile representation for compilation."""

    aliases: Dict[str, SiteAlias]
    raw: Dict[str, object]


@dataclass
class CompiledStep:
    """ActionPlan step representation."""

    t: str
    selector: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    kind: Optional[str] = None


@dataclass
class CompilationResult:
    """Final compiled ActionPlan data."""

    test_id: str
    base_url: str
    steps: List[CompiledStep]
    plan_dir: Path
    case_dir: Path
