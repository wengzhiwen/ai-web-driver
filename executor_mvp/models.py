"""Data models for the executor MVP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ActionStep:
    """Represents a single action in the DSL."""

    t: str
    selector: Optional[str] = None
    url: Optional[str] = None
    value: Optional[str] = None
    kind: Optional[str] = None


@dataclass
class ActionPlan:
    """Represents the loaded action plan."""

    test_id: str
    base_url: str
    steps: List[ActionStep]


@dataclass
class StepResult:
    """Captures outcome data for a single step."""

    index: int
    action: ActionStep
    status: str
    started_at: datetime
    finished_at: datetime
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    current_url: Optional[str] = None
    page_title: Optional[str] = None
    dom_size_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "t": self.action.t,
            "selector": self.action.selector,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "error": self.error,
            "screenshot": self.screenshot_path,
            "current_url": self.current_url,
            "page_title": self.page_title,
            "dom_size_bytes": self.dom_size_bytes,
        }


@dataclass
class RunResult:
    """Aggregated run outcome."""

    run_id: str
    test_id: str
    status: str
    started_at: datetime
    finished_at: datetime
    steps: List[StepResult] = field(default_factory=list)
    artifacts_dir: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "test_id": self.test_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "steps": [step.to_dict() for step in self.steps],
            "artifacts_dir": self.artifacts_dir,
            "error": self.error,
        }
