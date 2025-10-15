"""标定工具 Web GUI MVP Flask 应用。"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from flask import Flask

from .routes.calibration import calibration_bp
from .routes.calibrations_api import calibrations_api_bp


def setup_logging(debug: bool = False) -> None:
    """设置日志配置。"""
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level)

    # 文件日志处理器
    file_handler = TimedRotatingFileHandler(
        log_dir / "calibration-web.log",
        when="midnight",
        encoding="utf-8",
        backupCount=7,
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.getLogger().addHandler(file_handler)


def create_app(debug: bool = False) -> Flask:
    """创建 Flask 应用实例。"""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.config["DEBUG"] = debug
    app.config["SECRET_KEY"] = "calibration-web-mvp-secret-key-change-in-production"

    # 设置日志
    setup_logging(debug)

    # 注册蓝图
    app.register_blueprint(calibration_bp)
    app.register_blueprint(calibrations_api_bp, url_prefix="/api")

    # 设置静态文件缓存
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    return app


def main() -> None:
    """主函数，用于启动应用。"""
    debug = "--debug" in sys.argv
    app = create_app(debug=debug)

    port = 5110
    if "--port" in sys.argv:
        port_index = sys.argv.index("--port")
        if port_index + 1 < len(sys.argv):
            port = int(sys.argv[port_index + 1])

    print(f"启动标定工具 Web GUI: http://localhost:{port}")
    print("按 Ctrl+C 停止服务")

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
