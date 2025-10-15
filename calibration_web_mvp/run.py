#!/usr/bin/env python3
"""
标定工具 Web GUI MVP 启动脚本。
"""
from __future__ import annotations

import sys
import os

# 添加父目录到 Python 路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration_web_mvp.app import main

if __name__ == "__main__":
    main()
