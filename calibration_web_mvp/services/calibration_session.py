"""标定工具会话管理服务。"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGGER = logging.getLogger("calibration.session")


class CalibrationSession:
    """标定会话，管理有头浏览器实例和页面交互。"""

    def __init__(self, session_id: str, url: str, viewport: Optional[Dict[str, int]] = None):
        self.session_id = session_id
        self.url = url
        self.viewport = viewport or {"width": 1280, "height": 720}
        self.created_at = datetime.now(timezone.utc)
        self.last_accessed = datetime.now(timezone.utc)

        # Playwright 相关
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # 高亮相关
        self.highlight_injected = False

    def start_browser(self) -> None:
        """启动有头浏览器。"""
        try:
            LOGGER.info("启动会话 %s 浏览器: %s", self.session_id, self.url)

            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False, args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-features=VizDisplayCompositor"])

            self.context = self.browser.new_context(viewport=self.viewport, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

            self.page = self.context.new_page()

            # 导航到目标页面
            self.page.goto(self.url, timeout=30000)

            # 注入高亮脚本
            self._inject_highlight_script()

            LOGGER.info("会话 %s 浏览器启动成功", self.session_id)

        except PlaywrightTimeoutError as exc:
            LOGGER.error("会话 %s 页面加载超时: %s", self.session_id, exc)
            self.cleanup()
            raise RuntimeError(f"页面加载超时: {exc}") from exc
        except Exception as exc:
            LOGGER.error("会话 %s 浏览器启动失败: %s", self.session_id, exc)
            self.cleanup()
            raise RuntimeError(f"浏览器启动失败: {exc}") from exc

    def _inject_highlight_script(self) -> None:
        """向页面注入高亮脚本。"""
        if not self.page or self.highlight_injected:
            return

        script = """
        (function() {
            // 移除已存在的高亮元素
            document.querySelectorAll('.calibration-highlight').forEach(el => el.remove());

            // 高亮样式
            const style = document.createElement('style');
            style.textContent = `
                .calibration-highlight {
                    position: absolute !important;
                    background-color: rgba(255, 165, 0, 0.3) !important;
                    border: 2px solid #ff6600 !important;
                    pointer-events: none !important;
                    z-index: 999999 !important;
                    box-sizing: border-box !important;
                    transition: all 0.2s ease !important;
                }

                .calibration-highlight.pulse {
                    animation: calibrationPulse 1s ease-in-out !important;
                }

                @keyframes calibrationPulse {
                    0% { background-color: rgba(255, 165, 0, 0.3); }
                    50% { background-color: rgba(255, 165, 0, 0.6); }
                    100% { background-color: rgba(255, 165, 0, 0.3); }
                }
            `;
            document.head.appendChild(style);

            // 高亮函数
            window.calibrationHighlight = function(domId, action = 'show') {
                const element = document.querySelector(`[data-dom-id="${domId}"]`);
                if (!element) {
                    return { success: false, message: 'Element not found' };
                }

                // 移除已存在的高亮
                document.querySelectorAll('.calibration-highlight').forEach(el => el.remove());

                if (action === 'show') {
                    const rect = element.getBoundingClientRect();
                    const highlight = document.createElement('div');
                    highlight.className = 'calibration-highlight';
                    highlight.style.cssText = `
                        left: ${rect.left + window.scrollX}px;
                        top: ${rect.top + window.scrollY}px;
                        width: ${rect.width}px;
                        height: ${rect.height}px;
                    `;
                    document.body.appendChild(highlight);

                    // 滚动到元素位置
                    element.scrollIntoView({ behavior: 'smooth', block: 'center' });

                    // 添加脉冲效果
                    setTimeout(() => highlight.classList.add('pulse'), 100);

                    return {
                        success: true,
                        message: 'Element highlighted',
                        rect: {
                            x: rect.left + window.scrollX,
                            y: rect.top + window.scrollY,
                            width: rect.width,
                            height: rect.height
                        }
                    };
                } else if (action === 'hide') {
                    document.querySelectorAll('.calibration-highlight').forEach(el => el.remove());
                    return { success: true, message: 'Highlight cleared' };
                }

                return { success: false, message: 'Unknown action' };
            };

            console.log('Calibration highlight script injected');
        })();
        """

        try:
            self.page.evaluate(script)
            self.highlight_injected = True
            LOGGER.info("会话 %s 高亮脚本注入成功", self.session_id)
        except Exception as exc:
            LOGGER.warning("会话 %s 高亮脚本注入失败: %s", self.session_id, exc)

    def highlight_element(self, dom_id: str, action: str = "show") -> Dict[str, Any]:
        """高亮或清除元素高亮。"""
        if not self.page or not self.highlight_injected:
            return {"success": False, "message": "Session not ready"}

        try:
            result = self.page.evaluate("window.calibrationHighlight && window.calibrationHighlight(domId, action)", {"domId": dom_id, "action": action})
            return result or {"success": False, "message": "Highlight function not available"}
        except Exception as exc:
            LOGGER.error("会话 %s 高亮元素失败: %s", self.session_id, exc)
            return {"success": False, "message": f"Highlight failed: {exc}"}

    def scroll_to_element(self, dom_id: str) -> bool:
        """滚动到指定元素。"""
        if not self.page:
            return False

        try:
            # 尝试通过 data-dom-id 找到元素并滚动
            self.page.evaluate(
                """
                (domId) => {
                    const element = document.querySelector(`[data-dom-id="${domId}"]`);
                    if (element) {
                        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        return true;
                    }
                    return false;
                }
                """, dom_id)
            return True
        except Exception as exc:
            LOGGER.error("会话 %s 滚动到元素失败: %s", self.session_id, exc)
            return False

    def extract_dom_tree(self, max_depth: int = 8, max_nodes: int = 1000) -> Dict[str, Any]:
        """提取当前页面的 DOM 树。"""
        if not self.page:
            return {}

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

                const domId = node.getAttribute('data-dom-id') || `dom-${++domIdCounter}`;
                if (!node.hasAttribute('data-dom-id')) {
                    node.setAttribute('data-dom-id', domId);
                }
                if (!node.hasAttribute('data-dom-path')) {
                    node.setAttribute('data-dom-path', computePath(node));
                }

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

            return snapshotNode(document.body, 0) || {};
        }
        """

        try:
            result = self.page.evaluate(script, {"maxDepth": max_depth, "maxNodes": max_nodes})
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            LOGGER.error("会话 %s DOM 树提取失败: %s", self.session_id, exc)
            return {}

    def extract_a11y_tree(self) -> Dict[str, Any]:
        """提取页面的可访问性树。"""
        if not self.page:
            return {}

        try:
            a11y_snapshot = self.page.accessibility.snapshot({"interestingOnly": False})
            return a11y_snapshot if isinstance(a11y_snapshot, dict) else {}
        except Exception as exc:
            LOGGER.warning("会话 %s 可访问性树提取失败: %s", self.session_id, exc)
            return {}

    def get_element_bounding_box(self, dom_id: str) -> Optional[Dict[str, float]]:
        """获取元素的边界框。"""
        if not self.page:
            return None

        try:
            bbox = self.page.evaluate(
                """
                (domId) => {
                    const element = document.querySelector(`[data-dom-id="${domId}"]`);
                    if (element) {
                        const rect = element.getBoundingClientRect();
                        return {
                            x: rect.left + window.scrollX,
                            y: rect.top + window.scrollY,
                            width: rect.width,
                            height: rect.height
                        };
                    }
                    return null;
                }
                """, dom_id)
            return bbox
        except Exception as exc:
            LOGGER.error("会话 %s 获取元素边界框失败: %s", self.session_id, exc)
            return None

    def persist_snapshot(self, snapshot_dir: Path) -> Optional[str]:
        """持久化当前页面快照。"""
        if not self.page:
            return None

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            snapshot_token = f"{self.session_id}_{timestamp}"

            snapshot_path = snapshot_dir / snapshot_token
            snapshot_path.mkdir(parents=True, exist_ok=True)

            # 保存 HTML
            html_content = self.page.content()
            (snapshot_path / "page.html").write_text(html_content, encoding="utf-8")

            # 保存 DOM 树
            dom_tree = self.extract_dom_tree()
            (snapshot_path / "dom_tree.json").write_text(json.dumps(dom_tree, ensure_ascii=False, indent=2), encoding="utf-8")

            # 保存 A11y 树
            a11y_tree = self.extract_a11y_tree()
            (snapshot_path / "a11y_tree.json").write_text(json.dumps(a11y_tree, ensure_ascii=False, indent=2), encoding="utf-8")

            # 保存元数据
            metadata = {
                "session_id": self.session_id,
                "snapshot_token": snapshot_token,
                "url": self.url,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "viewport": self.viewport,
            }
            (snapshot_path / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

            LOGGER.info("会话 %s 快照已保存: %s", self.session_id, snapshot_token)
            return snapshot_token

        except Exception as exc:
            LOGGER.error("会话 %s 快照保存失败: %s", self.session_id, exc)
            return None

    def is_alive(self) -> bool:
        """检查浏览器会话是否存活。"""
        try:
            if not self.page or not self.browser or not self.context:
                return False

            # 检查浏览器连接是否还活跃
            # 使用更轻量的检查方式
            if self.browser.is_connected():
                return True
            return False
        except Exception as exc:
            LOGGER.debug("会话 %s 存活检查失败: %s", self.session_id, exc)
            return False

    def update_last_accessed(self) -> None:
        """更新最后访问时间。"""
        self.last_accessed = datetime.now(timezone.utc)

    def cleanup(self) -> None:
        """清理浏览器资源。"""
        try:
            # 逐个清理资源，确保每个步骤都安全执行
            if self.page:
                try:
                    self.page.close()
                except Exception as exc:
                    LOGGER.debug("会话 %s 关闭页面失败: %s", self.session_id, exc)
                finally:
                    self.page = None

            if self.context:
                try:
                    self.context.close()
                except Exception as exc:
                    LOGGER.debug("会话 %s 关闭上下文失败: %s", self.session_id, exc)
                finally:
                    self.context = None

            if self.browser:
                try:
                    if self.browser.is_connected():
                        self.browser.close()
                except Exception as exc:
                    LOGGER.debug("会话 %s 关闭浏览器失败: %s", self.session_id, exc)
                finally:
                    self.browser = None

            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception as exc:
                    LOGGER.debug("会话 %s 停止 Playwright 失败: %s", self.session_id, exc)
                finally:
                    self.playwright = None

            self.highlight_injected = False
            LOGGER.info("会话 %s 浏览器资源已清理", self.session_id)
        except Exception as exc:
            LOGGER.error("会话 %s 清理资源失败: %s", self.session_id, exc)


class SessionManager:
    """会话管理器，负责创建和管理多个标定会话。"""

    def __init__(self, snapshots_dir: Path):
        self.snapshots_dir = snapshots_dir
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, CalibrationSession] = {}
        self.max_sessions = 5  # 最大并发会话数
        self.session_timeout = 3600  # 会话超时时间（秒）

    def create_session(self, url: str, viewport: Optional[Dict[str, int]] = None) -> CalibrationSession:
        """创建新的标定会话。"""
        # 检查会话数量限制
        if len(self.sessions) >= self.max_sessions:
            raise RuntimeError(f"已达到最大会话数限制 ({self.max_sessions})")

        # 生成唯一会话 ID
        session_id = str(uuid.uuid4())

        # 创建会话
        session = CalibrationSession(session_id, url, viewport)

        # 启动浏览器
        session.start_browser()

        # 添加到会话池
        self.sessions[session_id] = session

        LOGGER.info("创建会话成功: %s -> %s", session_id, url)
        return session

    def get_session(self, session_id: str) -> Optional[CalibrationSession]:
        """获取会话。"""
        session = self.sessions.get(session_id)
        if session:
            session.update_last_accessed()
            return session
        return None

    def close_session(self, session_id: str) -> bool:
        """关闭指定会话。"""
        session = self.sessions.pop(session_id, None)
        if session:
            session.cleanup()
            LOGGER.info("会话已关闭: %s", session_id)
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """清理过期会话。"""
        import time

        current_time = datetime.now(timezone.utc)
        expired_sessions = []

        for session_id, session in self.sessions.items():
            age_seconds = (current_time - session.last_accessed).total_seconds()
            if age_seconds > self.session_timeout or not session.is_alive():
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.close_session(session_id)

        if expired_sessions:
            LOGGER.info("清理了 %d 个过期会话", len(expired_sessions))

        return len(expired_sessions)

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息。"""
        session = self.get_session(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "url": session.url,
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat(),
            "viewport": session.viewport,
            "is_alive": session.is_alive(),
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃会话。"""
        sessions = []
        for session in self.sessions.values():
            sessions.append({
                "session_id": session.session_id,
                "url": session.url,
                "created_at": session.created_at.isoformat(),
                "last_accessed": session.last_accessed.isoformat(),
                "viewport": session.viewport,
                "is_alive": session.is_alive(),
            })
        return sessions

    def cleanup_all(self) -> None:
        """清理所有会话。"""
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)
        LOGGER.info("所有会话已清理")


# 全局会话管理器实例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例。"""
    global _session_manager
    if _session_manager is None:
        snapshots_dir = Path("tmp/snapshots")
        _session_manager = SessionManager(snapshots_dir)
    return _session_manager
