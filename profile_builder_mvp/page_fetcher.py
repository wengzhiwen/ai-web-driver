"""Utilities for fetching page snapshots via Playwright."""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .models import FetchOptions, FetchedPage

LOGGER = logging.getLogger("profile_builder.fetcher")


@contextmanager
def _playwright_context(headless: bool = True):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def _sanitize_dom_snapshot(snapshot: Dict[str, object], max_nodes: int) -> Dict[str, object]:
    """确保 DOM 摘要不会超过节点上限。"""

    def _trim(node: Dict[str, object], counter: list[int]) -> Optional[Dict[str, object]]:
        if counter[0] >= max_nodes:
            return None
        counter[0] += 1
        children = node.get("children")
        if isinstance(children, list):
            trimmed_children = []
            for child in children:
                if not isinstance(child, dict):
                    continue
                if counter[0] >= max_nodes:
                    break
                trimmed_child = _trim(child, counter)
                if trimmed_child:
                    trimmed_children.append(trimmed_child)
            node["children"] = trimmed_children
        return node

    counter = [0]
    result = _trim(dict(snapshot), counter)
    return result or {}


def _extract_dom(page, *, max_depth: int, max_nodes: int) -> Tuple[Dict[str, object], List[Dict[str, Any]]]:
    """从页面中提取结构化的 DOM 摘要。"""

    script = r"""
    (vars) => {
        const MAX_DEPTH = vars.maxDepth;
        const MAX_NODES = vars.maxNodes;
        let count = 0;
        const SKIP_TAGS = new Set([
            'script', 'style', 'noscript', 'iframe', 'embed', 'object', 'svg', 'path', 'defs', 'g', 'use',
            'meta', 'link', 'base', 'head'
        ]);

        const computePath = (node) => {
            const segments = [];
            let current = node;
            while (current && current.nodeType === Node.ELEMENT_NODE) {
                const tag = current.tagName.toLowerCase();
                if (current.id) {
                    segments.unshift(`${tag}#${current.id}`);
                    break;
                }
                const className = (current.className || '').trim();
                if (className) {
                    const first = className.split(/\s+/)[0];
                    segments.unshift(`${tag}.${first}`);
                } else {
                    segments.unshift(tag);
                }
                current = current.parentElement;
            }
            return segments.join(' > ');
        };

        const cleanText = (text) => {
            if (!text) return null;
            const trimmed = text.replace(/\s+/g, ' ').trim();
            if (!trimmed) return null;
            return trimmed.slice(0, 120);
        };

        const collectAttributes = (el) => {
            const attrs = {};
            if (el.id) attrs.id = el.id;
            if (el.className) attrs.class = String(el.className).trim();
            if (el.getAttribute('data-test')) attrs.dataTest = el.getAttribute('data-test');
            if (el.getAttribute('aria-label')) attrs.ariaLabel = el.getAttribute('aria-label');
            if (el.getAttribute('role')) attrs.role = el.getAttribute('role');
            if (el.getAttribute('name')) attrs.nameAttr = el.getAttribute('name');
            if (el.getAttribute('value')) attrs.value = el.getAttribute('value');
            if (el.getAttribute('placeholder')) attrs.placeholder = el.getAttribute('placeholder');
            if (el.getAttribute('type')) attrs.type = el.getAttribute('type');
            // 过滤掉脚本相关属性，减少LLM噪音
            // 注意：我们只收集有用的测试相关属性，不收集 onclick, onload 等脚本事件
            return attrs;
        };

        const snapshotNode = (node, depth) => {
            if (count >= MAX_NODES) return null;
            if (depth > MAX_DEPTH) return null;
            if (!node || node.nodeType !== Node.ELEMENT_NODE) return null;
            if (SKIP_TAGS.has(node.tagName.toLowerCase())) return null;
            count += 1;

            const entry = {
                tag: node.tagName.toLowerCase(),
                depth,
                attrs: collectAttributes(node),
                path: computePath(node),
            };

            const text = cleanText(node.innerText ? node.innerText : '');
            if (text) entry.text = text;

            const childEntries = [];
            for (const child of node.children) {
                if (count >= MAX_NODES) break;
                const childSnapshot = snapshotNode(child, depth + 1);
                if (childSnapshot) childEntries.push(childSnapshot);
            }
            if (childEntries.length) entry.children = childEntries;
            return entry;
        };

        const collectControls = () => {
            const elements = document.querySelectorAll('input, textarea, select, button');
            return Array.from(elements).map((el) => ({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                className: (el.className || '').trim() || null,
                role: el.getAttribute('role') || null,
                nameAttr: el.getAttribute('name') || null,
                type: el.getAttribute('type') || null,
                ariaLabel: el.getAttribute('aria-label') || null,
                dataTest: el.getAttribute('data-test') || null,
                placeholder: el.getAttribute('placeholder') || null,
                path: computePath(el),
            }));
        };

        return {
            tree: snapshotNode(document.body, 0) || {},
            controls: collectControls(),
        };
    }
    """

    result = page.evaluate(script, {"maxDepth": max_depth, "maxNodes": max_nodes})
    if not isinstance(result, dict):
        return {}, [], {"max_depth": 0, "node_count": 0}
    tree = result.get("tree") if isinstance(result.get("tree"), dict) else {}
    controls = result.get("controls") if isinstance(result.get("controls"), list) else []
    sanitized_tree = _sanitize_dom_snapshot(tree, max_nodes)
    sanitized_controls = [control for control in controls if isinstance(control, dict)]
    stats = {
        "max_depth": _max_depth(sanitized_tree),
        "node_count": _count_nodes(sanitized_tree),
    }
    return sanitized_tree, sanitized_controls, stats


def _count_nodes(node: Dict[str, object]) -> int:
    count = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        count += 1
        children = current.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return count


def _max_depth(node: Dict[str, object]) -> int:
    max_depth = 0
    stack = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        depth = current.get("depth")
        if isinstance(depth, int):
            max_depth = max(max_depth, depth)
        children = current.get("children")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return max_depth


def fetch_page(
    url: str,
    *,
    options: Optional[FetchOptions] = None,
    output_dir: Optional[Path] = None,
    headless: bool = True,
    max_depth: int = 8,
    max_nodes: int = 1000,
) -> FetchedPage:
    """Fetch a page and return structured data for annotation."""

    opts = options or FetchOptions()
    LOGGER.info("Fetching %s", url)
    with _playwright_context(headless=headless) as page:
        try:
            page.goto(url, timeout=opts.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"页面加载超时: {exc}") from exc

        if opts.wait_for:
            try:
                page.wait_for_selector(opts.wait_for, timeout=opts.timeout_ms)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(f"等待元素 {opts.wait_for} 超时") from exc

        title = page.title() or ""
        html = page.content()
        dom_summary, controls, stats = _extract_dom(page, max_depth=max_depth, max_nodes=max_nodes)
        screenshot_path: Optional[Path] = None

        if opts.include_screenshot and output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = output_dir / "page.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as exc:  # pragma: no cover - best effort trace
                LOGGER.warning("截图失败: %s", exc)
                screenshot_path = None

    fetched = FetchedPage(
        url=url,
        title=title,
        html=html,
        dom_summary=dom_summary,
        fetched_at=datetime.utcnow(),
        screenshot_path=screenshot_path,
        controls=controls,
        stats=stats,
    )

    debug_dir: Optional[Path] = None
    if output_dir is not None:
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
    if debug_dir:
        snapshot_path = debug_dir / "dom_summary.json"
        snapshot_path.write_text(json.dumps(dom_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        html_path = debug_dir / "page.html"
        html_path.write_text(html, encoding="utf-8")

    return fetched
