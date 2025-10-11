"""Helpers for loading action plans."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ActionPlan, ActionStep


def _ensure_path(source: Any) -> Path:
    if isinstance(source, (str, Path)):
        return Path(source)
    raise TypeError(f"Unsupported path type: {type(source)!r}")


def load_json(source: Any) -> Dict[str, Any]:
    path = _ensure_path(source)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_action_plan(source: Any) -> ActionPlan:
    raw = load_json(source)

    meta = raw.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Action plan missing 'meta' object")

    test_id = meta.get("testId")
    base_url = meta.get("baseUrl")
    if not test_id or not base_url:
        raise ValueError("Action plan meta must include 'testId' and 'baseUrl'")

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Action plan must include 'steps' list")

    steps: list[ActionStep] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("Each step must be an object")
        t = raw_step.get("t")
        if not t:
            raise ValueError("Each step requires a 't' field")
        step = ActionStep(
            t=t,
            selector=raw_step.get("selector"),
            url=raw_step.get("url"),
            value=raw_step.get("value"),
            kind=raw_step.get("kind"),
        )
        steps.append(step)

    if not steps:
        raise ValueError("Action plan contains no steps")

    return ActionPlan(test_id=test_id, base_url=base_url, steps=steps)


def load_plan_from_directory(plan_dir: Any, case_name: Optional[str] = None) -> ActionPlan:
    root = _ensure_path(plan_dir)
    if not root.exists():
        raise FileNotFoundError(f"Plan directory '{root}' not found")

    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise FileNotFoundError(f"Cases directory not found at '{cases_dir}'")

    if case_name:
        case_dir = cases_dir / case_name
        if not case_dir.is_dir():
            raise FileNotFoundError(f"Case '{case_name}' not found under '{cases_dir}'")
    else:
        candidates = [path for path in cases_dir.iterdir() if path.is_dir()]
        if not candidates:
            raise FileNotFoundError(f"No cases found under '{cases_dir}'")
        if len(candidates) > 1:
            options = ", ".join(candidate.name for candidate in candidates)
            raise ValueError(
                "Multiple cases found; specify one via --case (available: " + options + ")"
            )
        case_dir = candidates[0]

    plan_path = case_dir / "action_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"Action plan not found at '{plan_path}'")

    return load_action_plan(plan_path)
