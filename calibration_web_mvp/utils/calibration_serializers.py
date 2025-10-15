"""标定工具序列化工具和响应格式化函数。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def create_success_response(data: Any = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """创建成功响应。"""
    response = {
        "success": True,
        "data": data,
        "error": None,
        "meta": meta or {},
    }
    return response


def create_error_response(code: str, message: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """创建错误响应。"""
    response = {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
        },
        "meta": meta or {},
    }
    return response


def serialize_dom_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """序列化单个 DOM 节点。"""
    return {
        "dom_id": node.get("dom_id"),
        "tag": node.get("tag"),
        "depth": node.get("depth"),
        "attrs": node.get("attrs", {}),
        "path": node.get("path"),
        "text": node.get("text"),
        "has_children": bool(node.get("children")),
    }


def serialize_dom_tree(tree: Dict[str, Any], max_depth: Optional[int] = None) -> Dict[str, Any]:
    """序列化 DOM 树。"""

    def _serialize_node(node: Dict[str, Any], current_depth: int = 0) -> Optional[Dict[str, Any]]:
        if max_depth is not None and current_depth > max_depth:
            return None

        serialized = serialize_dom_node(node)

        children = node.get("children")
        if isinstance(children, list) and children:
            serialized_children = []
            for child in children:
                if isinstance(child, dict):
                    serialized_child = _serialize_node(child, current_depth + 1)
                    if serialized_child:
                        serialized_children.append(serialized_child)
            if serialized_children:
                serialized["children"] = serialized_children

        return serialized

    return _serialize_node(tree) if tree else {}


def serialize_control(control: Dict[str, Any]) -> Dict[str, Any]:
    """序列化控件信息。"""
    return {
        "dom_id": control.get("dom_id"),
        "tag": control.get("tag"),
        "id": control.get("id"),
        "class": control.get("className"),
        "role": control.get("role"),
        "name": control.get("nameAttr"),
        "type": control.get("type"),
        "aria_label": control.get("ariaLabel"),
        "data_test": control.get("dataTest"),
        "placeholder": control.get("placeholder"),
        "path": control.get("path"),
    }


def serialize_a11y_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """序列化可访问性节点。"""
    return {
        "role": node.get("role"),
        "name": node.get("name"),
        "value": node.get("value"),
        "description": node.get("description"),
        "children": node.get("children", []),
    }


def serialize_snapshot_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """序列化快照元数据。"""
    return {
        "snapshot_id": metadata.get("snapshot_id"),
        "url": metadata.get("url"),
        "title": metadata.get("title"),
        "created_at": metadata.get("created_at"),
        "stats": metadata.get("stats", {}),
        "options": metadata.get("options", {}),
    }


def serialize_calibration_element(element: Dict[str, Any]) -> Dict[str, Any]:
    """序列化标定元素。"""
    return {
        "alias": element.get("alias"),
        "selector": element.get("selector"),
        "description": element.get("description"),
        "role": element.get("role"),
        "locator_strategy": element.get("locator_strategy", "dom_path"),
        "dom_id": element.get("dom_id"),
        "bounding_box": element.get("bounding_box"),
        "a11y": element.get("a11y"),
    }


def serialize_site_profile_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """序列化 Site Profile 请求。"""
    return {
        "snapshot_id": request.get("snapshot_id"),
        "site": request.get("site", {}),
        "page": request.get("page", {}),
        "elements": [serialize_calibration_element(el) for el in request.get("elements", [])],
    }


def serialize_validation_errors(errors: List[str]) -> Dict[str, Any]:
    """序列化验证错误列表。"""
    return {
        "errors": errors,
        "count": len(errors),
    }


def build_pagination_meta(page: int, per_page: int, total: int, pages: int) -> Dict[str, Any]:
    """构建分页元信息。"""
    return {
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
        }
    }


def create_snapshot_response(snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建快照响应。"""
    return create_success_response({
        "snapshot_id": snapshot_data.get("snapshot_id"),
        "url": snapshot_data.get("url"),
        "title": snapshot_data.get("title"),
        "stats": snapshot_data.get("stats", {}),
        "dom_tree": serialize_dom_tree(snapshot_data.get("dom_tree", {})),
        "controls": [serialize_control(control) for control in snapshot_data.get("controls", [])],
        "a11y_tree": snapshot_data.get("a11y_tree", {}),
    })


def create_site_profile_response(profile_path: str, created: bool = True) -> Dict[str, Any]:
    """创建 Site Profile 保存响应。"""
    from pathlib import Path

    path = Path(profile_path)
    return create_success_response({
        "profile_path": str(path),
        "filename": path.name,
        "created": created,
        "message": f"Site Profile 已{'创建' if created else '更新'}: {path.name}",
    })
