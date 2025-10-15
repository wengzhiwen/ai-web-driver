"""标定工具快照抓取与缓存管理服务。"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGGER = logging.getLogger("calibration.snapshot")


@contextmanager
def _playwright_context(headless: bool = True):
    """创建 Playwright 上下文。"""
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


def _extract_dom_with_ids(page, *, max_depth: int, max_nodes: int) -> Tuple[Dict[str, object], List[Dict[str, Any]]]:
    """从页面中提取结构化的 DOM 摘要，并注入 data-dom-id。"""

    script = r"""
    (vars) => {
        const MAX_DEPTH = vars.maxDepth;
        const MAX_NODES = vars.maxNodes;
        let count = 0;
        let domIdCounter = 0;
        const SKIP_TAGS = new Set([
            'script', 'style', 'noscript', 'svg', 'path', 'defs', 'g', 'use',
            'meta', 'link'
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
            return attrs;
        };

        const snapshotNode = (node, depth) => {
            if (count >= MAX_NODES) return null;
            if (depth > MAX_DEPTH) return null;
            if (!node || node.nodeType !== Node.ELEMENT_NODE) return null;
            if (SKIP_TAGS.has(node.tagName.toLowerCase())) return null;
            count += 1;

            const domId = `dom-${++domIdCounter}`;
            node.setAttribute('data-dom-id', domId);
            node.setAttribute('data-dom-path', computePath(node));

            const entry = {
                dom_id: domId,
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
            return Array.from(elements).map((el) => {
                const domId = el.getAttribute('data-dom-id');
                return {
                    dom_id: domId,
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
                };
            });
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


def _extract_a11y_tree(page) -> Dict[str, Any]:
    """提取页面的可访问性树。"""
    try:
        a11y_snapshot = page.accessibility.snapshot({"interestingOnly": False})
        return a11y_snapshot if isinstance(a11y_snapshot, dict) else {}
    except Exception as exc:
        LOGGER.warning("提取可访问性树失败: %s", exc)
        return {}


def _inject_dom_ids_to_html(html: str) -> str:
    """向 HTML 中注入 data-dom-id 属性的脚本。"""
    injection_script = """
<script>
(function() {
    let domIdCounter = 0;
    function injectIds(node) {
        if (node.nodeType === Node.ELEMENT_NODE && !node.hasAttribute('data-dom-id')) {
            node.setAttribute('data-dom-id', 'dom-' + (++domIdCounter));
        }
        for (let child of node.children) {
            injectIds(child);
        }
    }
    if (document.body) {
        injectIds(document.body);
    }

    // 高亮通信函数
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'highlight') {
            const domId = event.data.domId;
            const element = document.querySelector('[data-dom-id="' + domId + '"]');
            if (element) {
                // 移除之前的高亮
                document.querySelectorAll('.calibration-highlight').forEach(el => {
                    el.remove();
                });

                // 创建高亮遮罩
                const rect = element.getBoundingClientRect();
                const highlight = document.createElement('div');
                highlight.className = 'calibration-highlight';
                highlight.style.cssText = `
                    position: absolute;
                    left: ${rect.left + window.scrollX}px;
                    top: ${rect.top + window.scrollY}px;
                    width: ${rect.width}px;
                    height: ${rect.height}px;
                    background-color: rgba(255, 165, 0, 0.3);
                    border: 2px solid #ff6600;
                    pointer-events: none;
                    z-index: 999999;
                    box-sizing: border-box;
                `;
                document.body.appendChild(highlight);
                element.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else if (event.data && event.data.type === 'clear-highlight') {
            document.querySelectorAll('.calibration-highlight').forEach(el => {
                el.remove();
            });
        }
    });
})();
</script>
"""
    # 在 </body> 标签前注入脚本
    if "</body>" in html:
        return html.replace("</body>", injection_script + "</body>")
    else:
        return html + injection_script


def _count_nodes(node: Dict[str, object]) -> int:
    """计算节点数量。"""
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
    """计算最大深度。"""
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


class SnapshotManager:
    """快照管理器，负责创建和管理页面快照。"""

    def __init__(self, snapshots_dir: Path):
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(
        self,
        url: str,
        *,
        wait_for: Optional[str] = None,
        timeout: int = 10000,
        max_depth: int = 8,
        max_nodes: int = 1000,
        headless: bool = True,
    ) -> Dict[str, Any]:
        """创建页面快照。"""
        snapshot_id = str(uuid.uuid4())
        snapshot_dir = self.snapshots_dir / snapshot_id
        snapshot_dir.mkdir(exist_ok=True)

        LOGGER.info("创建快照 %s: %s", snapshot_id, url)

        try:
            with _playwright_context(headless=headless) as page:
                # 加载页面
                page.goto(url, timeout=timeout)

                if wait_for:
                    page.wait_for_selector(wait_for, timeout=timeout)

                title = page.title() or ""
                original_html = page.content()

                # 提取 DOM 树并注入 ID
                dom_tree, controls, stats = _extract_dom_with_ids(page, max_depth=max_depth, max_nodes=max_nodes)

                # 获取注入后的 HTML
                modified_html = page.content()
                modified_html = _inject_dom_ids_to_html(modified_html)

                # 提取可访问性树
                a11y_tree = _extract_a11y_tree(page)

                # 保存快照文件
                snapshot_data = {
                    "snapshot_id": snapshot_id,
                    "url": url,
                    "title": title,
                    "created_at": datetime.utcnow().isoformat(),
                    "stats": stats,
                    "options": {
                        "wait_for": wait_for,
                        "timeout": timeout,
                        "max_depth": max_depth,
                        "max_nodes": max_nodes,
                    },
                }

                # 保存元数据
                (snapshot_dir / "metadata.json").write_text(json.dumps(snapshot_data, ensure_ascii=False, indent=2), encoding="utf-8")

                # 保存 HTML
                (snapshot_dir / "page.html").write_text(modified_html, encoding="utf-8")

                # 保存 DOM 树
                (snapshot_dir / "dom_tree.json").write_text(json.dumps(dom_tree, ensure_ascii=False, indent=2), encoding="utf-8")

                # 保存控件列表
                (snapshot_dir / "controls.json").write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")

                # 保存可访问性树
                (snapshot_dir / "a11y_tree.json").write_text(json.dumps(a11y_tree, ensure_ascii=False, indent=2), encoding="utf-8")

                LOGGER.info("快照创建成功: %s (节点数: %s)", snapshot_id, stats.get("node_count", 0))

                return {
                    "snapshot_id": snapshot_id,
                    "url": url,
                    "title": title,
                    "stats": stats,
                    "dom_tree": dom_tree,
                    "controls": controls,
                    "a11y_tree": a11y_tree,
                }

        except PlaywrightTimeoutError as exc:
            LOGGER.error("页面加载超时: %s", exc)
            raise RuntimeError(f"页面加载超时: {exc}") from exc
        except Exception as exc:
            LOGGER.error("创建快照失败: %s", exc)
            # 清理失败的快照目录
            if snapshot_dir.exists():
                import shutil
                shutil.rmtree(snapshot_dir)
            raise RuntimeError(f"创建快照失败: {exc}") from exc

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """获取快照数据。"""
        snapshot_dir = self.snapshots_dir / snapshot_id
        if not snapshot_dir.exists():
            return None

        try:
            metadata_file = snapshot_dir / "metadata.json"
            dom_tree_file = snapshot_dir / "dom_tree.json"
            controls_file = snapshot_dir / "controls.json"
            a11y_tree_file = snapshot_dir / "a11y_tree.json"
            html_file = snapshot_dir / "page.html"

            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            dom_tree = json.loads(dom_tree_file.read_text(encoding="utf-8"))
            controls = json.loads(controls_file.read_text(encoding="utf-8"))
            a11y_tree = json.loads(a11y_tree_file.read_text(encoding="utf-8"))
            html_content = html_file.read_text(encoding="utf-8")

            return {
                "metadata": metadata,
                "dom_tree": dom_tree,
                "controls": controls,
                "a11y_tree": a11y_tree,
                "html_content": html_content,
            }
        except Exception as exc:
            LOGGER.error("读取快照失败 %s: %s", snapshot_id, exc)
            return None

    def cleanup_old_snapshots(self, days: int = 1) -> int:
        """清理旧的快照文件。"""
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(days=days)
        cleaned_count = 0

        for snapshot_dir in self.snapshots_dir.iterdir():
            if not snapshot_dir.is_dir():
                continue

            try:
                metadata_file = snapshot_dir / "metadata.json"
                if metadata_file.exists():
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    created_at = datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
                    if created_at < cutoff_time:
                        import shutil
                        shutil.rmtree(snapshot_dir)
                        cleaned_count += 1
                        LOGGER.info("清理旧快照: %s", snapshot_dir.name)
                else:
                    # 没有元数据文件的目录也清理掉
                    import shutil
                    shutil.rmtree(snapshot_dir)
                    cleaned_count += 1
            except Exception as exc:
                LOGGER.warning("清理快照失败 %s: %s", snapshot_dir.name, exc)

        if cleaned_count > 0:
            LOGGER.info("清理完成，删除了 %d 个旧快照", cleaned_count)

        return cleaned_count


# 全局快照管理器实例
_snapshot_manager: Optional[SnapshotManager] = None


def get_snapshot_manager() -> SnapshotManager:
    """获取全局快照管理器实例。"""
    global _snapshot_manager
    if _snapshot_manager is None:
        snapshots_dir = Path("tmp/snapshots")
        _snapshot_manager = SnapshotManager(snapshots_dir)
    return _snapshot_manager
