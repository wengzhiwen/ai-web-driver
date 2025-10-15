"""标定工具传统视图路由。"""
from __future__ import annotations

import logging
from flask import Blueprint, render_template, request, jsonify

from ..services.calibration_snapshot import get_snapshot_manager

LOGGER = logging.getLogger("calibration.routes")

calibration_bp = Blueprint("calibration", __name__)


@calibration_bp.route("/")
def index():
    """标定工具主页。"""
    return render_template("calibration.html")


@calibration_bp.route("/health")
def health():
    """健康检查端点。"""
    return jsonify({"status": "ok", "service": "calibration-web-mvp"})


@calibration_bp.route("/cleanup", methods=["POST"])
def cleanup_snapshots():
    """清理旧快照。"""
    try:
        manager = get_snapshot_manager()
        cleaned_count = manager.cleanup_old_snapshots(days=1)
        return jsonify({"success": True, "cleaned_count": cleaned_count, "message": f"清理了 {cleaned_count} 个旧快照"})
    except Exception as exc:
        LOGGER.error("清理快照失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
