"""Parses natural language test request documents."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from .models import TestRequest, TestStep

URL_PATTERN = re.compile(r"https?://[\w\-./?=#%&:+]+", re.IGNORECASE)
STEP_PATTERN = re.compile(r"^\s*(\d+)[\.|、]\s*(.+)$")


def parse_markdown(path: Path) -> TestRequest:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = ""
    steps: List[TestStep] = []
    for line in lines:
        if not title and line.startswith("#"):
            title = line.lstrip("# ").strip()
            continue

        match = STEP_PATTERN.match(line)
        if match:
            step_index = int(match.group(1))
            step_text = match.group(2).strip()
            steps.append(TestStep(index=step_index, text=step_text))

    if not title:
        title = path.stem

    base_url_match = URL_PATTERN.search(text)
    base_url = base_url_match.group(0) if base_url_match else None

    return TestRequest(title=title, base_url=base_url, steps=steps, source_path=path)
