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


# pylint: disable=too-many-branches
def load_plan_from_directory(plan_dir: Any, case_name: Optional[str] = None) -> ActionPlan:
    """Load action plan from directory structure.
    
    Supports multiple formats:
    1. Directory with subdirectory: plan_dir/cases/case_name/action_plan.json
    2. Direct JSON file: plan_dir/cases/case_name.json
    3. Auto-detect single case
    
    Args:
        plan_dir: Root plan directory.
        case_name: Case name, directory name, or JSON filename (with or without .json).
    
    Returns:
        Loaded ActionPlan.
    """
    root = _ensure_path(plan_dir)
    if not root.exists():
        raise FileNotFoundError(f"Plan directory '{root}' not found")

    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise FileNotFoundError(f"Cases directory not found at '{cases_dir}'")

    if case_name:
        # 尝试多种加载方式

        # 1. 尝试作为子目录
        case_dir = cases_dir / case_name
        if case_dir.is_dir():
            plan_path = case_dir / "action_plan.json"
            if plan_path.exists():
                return load_action_plan(plan_path)

        # 2. 尝试作为JSON文件（带.json后缀）
        if case_name.endswith('.json'):
            json_file = cases_dir / case_name
            if json_file.is_file():
                return load_action_plan(json_file)

        # 3. 尝试添加.json后缀
        json_file = cases_dir / f"{case_name}.json"
        if json_file.is_file():
            return load_action_plan(json_file)

        # 4. 尝试查找包含case_name的文件
        for item in cases_dir.iterdir():
            if item.is_file() and item.suffix == '.json':
                if case_name in item.stem or item.stem == case_name:
                    return load_action_plan(item)

        raise FileNotFoundError(f"Case '{case_name}' not found under '{cases_dir}' "
                                f"(tried directory, .json file, and pattern matching)")
    else:
        # 自动检测
        # 优先查找子目录
        dir_candidates = [path for path in cases_dir.iterdir() if path.is_dir()]

        # 同时查找JSON文件
        json_candidates = [path for path in cases_dir.iterdir() if path.is_file() and path.suffix == '.json']

        if len(dir_candidates) == 1:
            case_dir = dir_candidates[0]
            plan_path = case_dir / "action_plan.json"
            if plan_path.exists():
                return load_action_plan(plan_path)

        if len(json_candidates) == 1:
            return load_action_plan(json_candidates[0])

        if not dir_candidates and not json_candidates:
            raise FileNotFoundError(f"No cases found under '{cases_dir}'")

        all_options = [d.name for d in dir_candidates] + [f.name for f in json_candidates]
        options = ", ".join(all_options[:5])
        if len(all_options) > 5:
            options += f", ... ({len(all_options)} total)"
        raise ValueError(f"Multiple cases found; specify one via --case (available: {options})")
