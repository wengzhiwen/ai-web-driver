"""Data structures used by the compiler MVP."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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


@dataclass
class DataItem:
    """A single data item for data-driven compilation."""

    index: int
    data: Dict[str, Any]


@dataclass
class DataSet:
    """Collection of data items for data-driven test generation."""

    category: str
    items: List[DataItem] = field(default_factory=list)
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class PlaceholderMatch:
    """Information about a matched placeholder."""

    placeholder: str
    field_name: str
    multiplier: Optional[int] = None
    is_gender_translation: bool = False

    def is_expression(self) -> bool:
        """Check if this is an expression placeholder (with multiplier)."""
        return self.multiplier is not None


@dataclass
class ReplacementError:
    """Error encountered during placeholder replacement."""

    error_type: str
    placeholder: str
    field_name: str
    data_index: int
    message: str


@dataclass
class ReplacementStats:
    """Statistics for placeholder replacement process."""

    total_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    errors: List[ReplacementError] = field(default_factory=list)

    def get_error_summary(self) -> Dict[str, int]:
        """Get count of errors by type."""
        summary: Dict[str, int] = {}
        for error in self.errors:
            summary[error.error_type] = summary.get(error.error_type, 0) + 1
        return summary


@dataclass
class DataDrivenResult:
    """Result of data-driven compilation."""

    template_plan: Dict[str, object]
    test_id_base: str
    base_url: str
    cases: List[Dict[str, object]] = field(default_factory=list)
    stats: ReplacementStats = field(default_factory=ReplacementStats)
    plan_dir: Path = None
    case_dir: Path = None
