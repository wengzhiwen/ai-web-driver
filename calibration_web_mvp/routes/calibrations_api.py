"""标定工具 REST API 路由。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from ..services.calibration_session import get_session_manager
from ..services.calibration_snapshot import get_snapshot_manager
from ..utils.calibration_serializers import (
    create_success_response,
    create_error_response,
    create_snapshot_response,
    create_site_profile_response,
    serialize_site_profile_request,
)

LOGGER = logging.getLogger("calibration.api")

calibrations_api_bp = Blueprint("calibrations_api", __name__)

# ==================== 会话管理 API ====================


@calibrations_api_bp.route("/calibrations/sessions", methods=["POST"])
def create_session():
    """创建新的标定会话。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(create_error_response("INVALID_REQUEST", "请求体不能为空")), 400

        url = data.get("url")
        if not url:
            return jsonify(create_error_response("MISSING_URL", "缺少 URL 参数")), 400

        viewport = data.get("viewport", {"width": 1280, "height": 720})

        LOGGER.info("创建会话请求: URL=%s, viewport=%s", url, viewport)

        session_manager = get_session_manager()

        # 清理过期会话
        session_manager.cleanup_expired_sessions()

        # 创建新会话
        session = session_manager.create_session(url, viewport)

        return jsonify(
            create_success_response({
                "session_id": session.session_id,
                "url": session.url,
                "viewport": session.viewport,
                "created_at": session.created_at.isoformat(),
                "message": "会话创建成功，已启动有头浏览器窗口"
            }))

    except RuntimeError as exc:
        LOGGER.error("创建会话失败: %s", exc)
        if "超时" in str(exc):
            return jsonify(create_error_response("TIMEOUT_ERROR", f"页面加载超时: {exc}")), 400
        elif "最大会话数" in str(exc):
            return jsonify(create_error_response("SESSION_LIMIT_EXCEEDED", str(exc))), 429
        else:
            return jsonify(create_error_response("SESSION_CREATE_FAILED", f"会话创建失败: {exc}")), 400
    except Exception as exc:
        LOGGER.error("创建会话异常: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/sessions/<session_id>", methods=["GET"])
def get_session_info(session_id: str):
    """获取会话信息。"""
    try:
        session_manager = get_session_manager()
        session_info = session_manager.get_session_info(session_id)

        if not session_info:
            return jsonify(create_error_response("SESSION_NOT_FOUND", f"会话不存在: {session_id}")), 404

        return jsonify(create_success_response(session_info))

    except Exception as exc:
        LOGGER.error("获取会话信息失败 %s: %s", session_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/sessions/<session_id>", methods=["DELETE"])
def close_session(session_id: str):
    """关闭指定会话。"""
    try:
        session_manager = get_session_manager()
        success = session_manager.close_session(session_id)

        if not success:
            return jsonify(create_error_response("SESSION_NOT_FOUND", f"会话不存在: {session_id}")), 404

        return jsonify(create_success_response({"message": f"会话 {session_id} 已关闭"}))

    except Exception as exc:
        LOGGER.error("关闭会话失败 %s: %s", session_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/sessions/<session_id>/dom-sync", methods=["POST"])
def sync_dom_tree(session_id: str):
    """同步 DOM 树数据。"""
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            return jsonify(create_error_response("SESSION_NOT_FOUND", f"会话不存在: {session_id}")), 404

        if not session.is_alive():
            return jsonify(create_error_response("SESSION_CLOSED", "会话已关闭，请重新创建会话")), 410

        data = request.get_json() or {}
        max_depth = data.get("max_depth", 8)
        max_nodes = data.get("max_nodes", 1000)
        include_bounding_box = data.get("include_bounding_box", False)
        include_accessibility = data.get("include_accessibility", True)

        # 提取 DOM 树
        dom_tree = session.extract_dom_tree(max_depth=max_depth, max_nodes=max_nodes)

        # 提取控件列表
        controls = []
        if dom_tree:
            controls = _extract_controls_from_dom(dom_tree)

        # 提取可访问性树
        a11y_tree = {}
        if include_accessibility:
            a11y_tree = session.extract_a11y_tree()

        # 获取边界框信息（如果需要）
        if include_bounding_box and dom_tree:
            _add_bounding_boxes_to_dom(session, dom_tree)

        response_data = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dom_tree": dom_tree,
            "controls": controls,
            "a11y_tree": a11y_tree,
            "stats": {
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "node_count": _count_dom_nodes(dom_tree),
            }
        }

        return jsonify(create_success_response(response_data))

    except Exception as exc:
        LOGGER.error("同步 DOM 树失败 %s: %s", session_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", f"DOM 同步失败: {exc}")), 500


@calibrations_api_bp.route("/calibrations/sessions/<session_id>/highlight", methods=["POST"])
def highlight_element(session_id: str):
    """高亮或清除页面元素。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(create_error_response("INVALID_REQUEST", "请求体不能为空")), 400

        dom_id = data.get("dom_id")
        action = data.get("action", "show")
        selector = data.get("selector")

        if not dom_id and not selector:
            return jsonify(create_error_response("MISSING_IDENTIFIER", "缺少 dom_id 或 selector")), 400

        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            return jsonify(create_error_response("SESSION_NOT_FOUND", f"会话不存在: {session_id}")), 404

        if not session.is_alive():
            return jsonify(create_error_response("SESSION_CLOSED", "会话已关闭，请重新创建会话")), 410

        # 如果提供了 selector，尝试找到对应的 dom_id
        target_dom_id = dom_id
        if selector and not target_dom_id:
            target_dom_id = _find_dom_id_by_selector(session, selector)
            if not target_dom_id:
                return jsonify(create_error_response("ELEMENT_NOT_FOUND", f"未找到选择器对应的元素: {selector}")), 404

        # 执行高亮操作
        result = session.highlight_element(target_dom_id, action)

        if result.get("success"):
            return jsonify(
                create_success_response({
                    "dom_id": target_dom_id,
                    "action": action,
                    "message": result.get("message"),
                    "bounding_box": result.get("rect")
                }))
        else:
            return jsonify(create_error_response("HIGHLIGHT_FAILED", result.get("message", "高亮失败"))), 400

    except Exception as exc:
        LOGGER.error("高亮元素失败 %s: %s", session_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", f"高亮操作失败: {exc}")), 500


@calibrations_api_bp.route("/calibrations/sessions/<session_id>/persist-snapshot", methods=["POST"])
def persist_snapshot(session_id: str):
    """持久化页面快照。"""
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session(session_id)

        if not session:
            return jsonify(create_error_response("SESSION_NOT_FOUND", f"会话不存在: {session_id}")), 404

        if not session.is_alive():
            return jsonify(create_error_response("SESSION_CLOSED", "会话已关闭，请重新创建会话")), 410

        # 持久化快照
        snapshot_token = session.persist_snapshot(session_manager.snapshots_dir)

        if not snapshot_token:
            return jsonify(create_error_response("SNAPSHOT_FAILED", "快照保存失败")), 500

        return jsonify(create_success_response({"session_id": session_id, "snapshot_token": snapshot_token, "message": "快照已保存"}))

    except Exception as exc:
        LOGGER.error("持久化快照失败 %s: %s", session_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", f"快照保存失败: {exc}")), 500


@calibrations_api_bp.route("/calibrations/sessions", methods=["GET"])
def list_sessions():
    """列出所有活跃会话。"""
    try:
        session_manager = get_session_manager()
        sessions = session_manager.list_sessions()

        return jsonify(create_success_response({"sessions": sessions, "count": len(sessions), "max_sessions": session_manager.max_sessions}))

    except Exception as exc:
        LOGGER.error("列出会话失败: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/sessions/cleanup", methods=["POST"])
def cleanup_sessions():
    """清理过期会话。"""
    try:
        session_manager = get_session_manager()
        cleaned_count = session_manager.cleanup_expired_sessions()

        return jsonify(create_success_response({"cleaned_count": cleaned_count, "message": f"清理了 {cleaned_count} 个过期会话"}))

    except Exception as exc:
        LOGGER.error("清理会话失败: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


# ==================== 辅助函数 ====================


def _extract_controls_from_dom(dom_tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 DOM 树中提取控件信息。"""
    controls = []

    def _extract_recursive(node):
        if not isinstance(node, dict):
            return

        # 检查是否为可交互元素
        tag = node.get("tag", "")
        if tag in ["input", "textarea", "select", "button", "a"]:
            control = {
                "dom_id": node.get("dom_id"),
                "tag": tag,
                "attrs": node.get("attrs", {}),
                "path": node.get("path", ""),
                "text": node.get("text", ""),
            }
            controls.append(control)

        # 递归处理子节点
        children = node.get("children", [])
        for child in children:
            _extract_recursive(child)

    _extract_recursive(dom_tree)
    return controls


def _count_dom_nodes(dom_tree: Dict[str, Any]) -> int:
    """计算 DOM 节点数量。"""
    count = 0

    def _count_recursive(node):
        nonlocal count
        if not isinstance(node, dict):
            return

        count += 1
        children = node.get("children", [])
        for child in children:
            _count_recursive(child)

    _count_recursive(dom_tree)
    return count


def _add_bounding_boxes_to_dom(session, dom_tree: Dict[str, Any]) -> None:
    """为 DOM 树中的节点添加边界框信息。"""

    def _add_recursive(node):
        if not isinstance(node, dict):
            return

        dom_id = node.get("dom_id")
        if dom_id:
            bbox = session.get_element_bounding_box(dom_id)
            if bbox:
                node["bounding_box"] = bbox

        children = node.get("children", [])
        for child in children:
            _add_recursive(child)

    _add_recursive(dom_tree)


def _find_dom_id_by_selector(session, selector: str) -> Optional[str]:
    """通过选择器查找对应的 dom_id。"""
    try:
        # 使用 CSS 选择器找到元素，然后获取其 data-dom-id
        result = session.page.evaluate(
            """
            (selector) => {
                const element = document.querySelector(selector);
                if (element) {
                    return element.getAttribute('data-dom-id');
                }
                return null;
            }
            """, selector)
        return result
    except Exception:
        return None


@calibrations_api_bp.route("/calibrations/snapshots", methods=["POST"])
def create_snapshot():
    """创建页面快照。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(create_error_response("INVALID_REQUEST", "请求体不能为空")), 400

        url = data.get("url")
        if not url:
            return jsonify(create_error_response("MISSING_URL", "缺少 URL 参数")), 400

        wait_for = data.get("waitFor")
        timeout = data.get("timeout", 10000)
        max_depth = data.get("maxDepth", 8)
        max_nodes = data.get("maxNodes", 1000)
        headless = data.get("headless", True)

        LOGGER.info("创建快照请求: URL=%s, wait_for=%s, timeout=%d", url, wait_for, timeout)

        manager = get_snapshot_manager()
        snapshot_data = manager.create_snapshot(
            url=url,
            wait_for=wait_for,
            timeout=timeout,
            max_depth=max_depth,
            max_nodes=max_nodes,
            headless=headless,
        )

        return jsonify(create_snapshot_response(snapshot_data))

    except RuntimeError as exc:
        LOGGER.error("创建快照失败: %s", exc)
        if "超时" in str(exc):
            return jsonify(create_error_response("FETCH_ERROR", f"页面加载超时: {exc}")), 400
        else:
            return jsonify(create_error_response("FETCH_ERROR", f"页面抓取失败: {exc}")), 400
    except Exception as exc:
        LOGGER.error("创建快照异常: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/snapshots/<snapshot_id>", methods=["GET"])
def get_snapshot(snapshot_id: str):
    """获取快照数据。"""
    try:
        manager = get_snapshot_manager()
        snapshot = manager.get_snapshot(snapshot_id)

        if not snapshot:
            return jsonify(create_error_response("SNAPSHOT_NOT_FOUND", f"快照不存在: {snapshot_id}")), 404

        return jsonify(
            create_success_response({
                "metadata": snapshot["metadata"],
                "dom_tree": snapshot["dom_tree"],
                "controls": snapshot["controls"],
                "a11y_tree": snapshot["a11y_tree"],
                "html_content": snapshot["html_content"],
            }))

    except Exception as exc:
        LOGGER.error("获取快照失败 %s: %s", snapshot_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/snapshots/<snapshot_id>/html", methods=["GET"])
def get_snapshot_html(snapshot_id: str):
    """获取快照 HTML 内容。"""
    try:
        manager = get_snapshot_manager()
        snapshot = manager.get_snapshot(snapshot_id)

        if not snapshot:
            return jsonify(create_error_response("SNAPSHOT_NOT_FOUND", f"快照不存在: {snapshot_id}")), 404

        return snapshot["html_content"], 200, {"Content-Type": "text/html; charset=utf-8"}

    except Exception as exc:
        LOGGER.error("获取快照 HTML 失败 %s: %s", snapshot_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/snapshots/<snapshot_id>/highlight-check", methods=["POST"])
def highlight_check(snapshot_id: str):
    """验证选择器的高亮检查（预留接口）。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(create_error_response("INVALID_REQUEST", "请求体不能为空")), 400

        selector = data.get("selector")
        if not selector:
            return jsonify(create_error_response("MISSING_SELECTOR", "缺少选择器")), 400

        # MVP 阶段返回固定结果，后续可基于快照进行实际验证
        return jsonify(create_success_response({"selector": selector, "unique": True, "element_count": 1, "message": "选择器验证通过"}))

    except Exception as exc:
        LOGGER.error("高亮检查失败 %s: %s", snapshot_id, exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/site-profiles", methods=["POST"])
def save_site_profile():
    """保存 Site Profile。"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(create_error_response("INVALID_REQUEST", "请求体不能为空")), 400

        # 验证请求格式
        serialized_request = serialize_site_profile_request(data)
        snapshot_id = serialized_request.get("snapshot_id")
        site_info = serialized_request.get("site", {})
        page_info = serialized_request.get("page", {})
        elements = serialized_request.get("elements", [])

        if not snapshot_id:
            return jsonify(create_error_response("MISSING_SNAPSHOT_ID", "缺少快照 ID")), 400

        if not site_info.get("name"):
            return jsonify(create_error_response("MISSING_SITE_NAME", "缺少站点名称")), 400

        if not page_info.get("page_id"):
            return jsonify(create_error_response("MISSING_PAGE_ID", "缺少页面 ID")), 400

        if not elements:
            return jsonify(create_error_response("MISSING_ELEMENTS", "没有标定元素")), 400

        # 验证快照存在
        manager = get_snapshot_manager()
        snapshot = manager.get_snapshot(snapshot_id)
        if not snapshot:
            return jsonify(create_error_response("SNAPSHOT_NOT_FOUND", f"快照不存在: {snapshot_id}")), 404

        # 构建 Site Profile 结构
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        profile_data = {
            "version":
            timestamp,
            "site": {
                "name": site_info["name"],
                "base_url": site_info.get("base_url", snapshot["metadata"]["url"]),
            } if site_info else None,
            "pages": [{
                "page_id": page_info["page_id"],
                "url_pattern": page_info.get("url_pattern", snapshot["metadata"]["url"]),
                "version": timestamp,
                "generated_by": "calibration-web-mvp",
                "generated_at": timestamp,
                "summary": page_info.get("summary", ""),
                "aliases": {},
                "notes": page_info.get("notes", "人工标定草稿"),
                "snapshot_id": snapshot_id,
            }],
        }

        # 添加标定元素
        aliases = {}
        for element in elements:
            alias_name = element.get("alias")
            if not alias_name:
                continue

            alias_data = {
                "selector": element.get("selector"),
                "description": element.get("description"),
                "role": element.get("role"),
            }

            # 添加可选字段
            if element.get("dom_id"):
                alias_data["dom_id"] = element["dom_id"]
            if element.get("bounding_box"):
                alias_data["bounding_box"] = element["bounding_box"]
            if element.get("a11y"):
                alias_data["a11y"] = element["a11y"]
            if element.get("locator_strategy"):
                alias_data["locator_strategy"] = element["locator_strategy"]

            aliases[alias_name] = alias_data

        profile_data["pages"][0]["aliases"] = aliases

        # 保存到文件
        site_name = site_info["name"]
        page_id = page_info["page_id"]
        filename = f"{site_name}_{page_id}_{timestamp.replace(':', '').replace('-', '').replace('+', '')}.json"

        drafts_dir = Path("site_profiles/drafts")
        drafts_dir.mkdir(parents=True, exist_ok=True)

        profile_path = drafts_dir / filename
        profile_path.write_text(json.dumps(profile_data, ensure_ascii=False, indent=2), encoding="utf-8")

        LOGGER.info("Site Profile 已保存: %s", profile_path)

        return jsonify(create_site_profile_response(str(profile_path), created=True))

    except Exception as exc:
        LOGGER.error("保存 Site Profile 失败: %s", exc)
        return jsonify(create_error_response("SAVE_FAILED", f"保存失败: {exc}")), 500


@calibrations_api_bp.route("/calibrations/site-profiles", methods=["GET"])
def list_site_profiles():
    """列出已保存的 Site Profile 草稿。"""
    try:
        drafts_dir = Path("site_profiles/drafts")
        if not drafts_dir.exists():
            return jsonify(create_success_response({"profiles": [], "count": 0}))

        profiles = []
        for profile_file in drafts_dir.glob("*.json"):
            try:
                profile_data = json.loads(profile_file.read_text(encoding="utf-8"))
                profiles.append({
                    "filename": profile_file.name,
                    "path": str(profile_file),
                    "created_at": profile_data.get("pages", [{}])[0].get("generated_at"),
                    "site_name": profile_data.get("site", {}).get("name"),
                    "page_count": len(profile_data.get("pages", [])),
                })
            except Exception as exc:
                LOGGER.warning("读取 profile 文件失败 %s: %s", profile_file, exc)

        # 按创建时间倒序排列
        profiles.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return jsonify(create_success_response({
            "profiles": profiles,
            "count": len(profiles),
        }))

    except Exception as exc:
        LOGGER.error("列出 Site Profile 失败: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500


@calibrations_api_bp.route("/calibrations/debug/stats", methods=["GET"])
def get_debug_stats():
    """获取调试统计信息。"""
    try:
        manager = get_snapshot_manager()
        snapshots_dir = manager.snapshots_dir

        if not snapshots_dir.exists():
            return jsonify(create_success_response({
                "snapshot_count": 0,
                "total_size_mb": 0,
                "oldest_snapshot": None,
                "newest_snapshot": None,
            }))

        snapshot_count = 0
        total_size = 0
        oldest_time = None
        newest_time = None

        for snapshot_dir in snapshots_dir.iterdir():
            if not snapshot_dir.is_dir():
                continue

            snapshot_count += 1

            # 计算目录大小
            dir_size = sum(f.stat().st_size for f in snapshot_dir.rglob("*") if f.is_file())
            total_size += dir_size

            # 读取创建时间
            metadata_file = snapshot_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                    created_at = datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))

                    if oldest_time is None or created_at < oldest_time:
                        oldest_time = created_at
                    if newest_time is None or created_at > newest_time:
                        newest_time = created_at
                except Exception:
                    pass

        return jsonify(
            create_success_response({
                "snapshot_count": snapshot_count,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "oldest_snapshot": oldest_time.isoformat() if oldest_time else None,
                "newest_snapshot": newest_time.isoformat() if newest_time else None,
            }))

    except Exception as exc:
        LOGGER.error("获取调试统计失败: %s", exc)
        return jsonify(create_error_response("INTERNAL_ERROR", "服务器内部错误")), 500
