# 标定工具 Web GUI MVP

基于 Flask 的标定工具 Web GUI，提供页面抓取、DOM/A11y 树浏览、手动标定和 Site Profile 生成功能。

## 功能特性

- **页面抓取**：使用 Playwright 抓取目标页面，生成 DOM 树和可访问性树
- **可视化浏览**：左侧展示页面快照，右侧显示 DOM/A11y 树结构
- **联动高亮**：点击树节点时，左侧页面同步高亮显示对应元素
- **手动标定**：为页面元素添加别名、描述、定位器等信息
- **Site Profile 导出**：将标定结果保存为标准的 Site Profile JSON 格式

## 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

## 启动应用

```bash
# 基本启动
python run.py

# 调试模式启动
python run.py --debug

# 指定端口启动
python run.py --port 8080
```

启动后访问：http://localhost:5000

## 使用流程

1. **加载页面**：在顶部输入目标 URL，点击"加载页面"
2. **浏览 DOM 树**：在右侧 DOM 树标签页中浏览页面结构
3. **选择节点**：点击 DOM 树节点，左侧页面会高亮显示对应元素
4. **标定元素**：在弹出的节点信息窗口中填写别名、描述等信息
5. **保存配置**：在"标定列表"标签页中点击"保存 Site Profile"

## API 接口

### 创建快照
```
POST /api/calibrations/snapshots
Content-Type: application/json

{
  "url": "https://example.com",
  "waitFor": null,
  "timeout": 10000,
  "maxDepth": 8,
  "maxNodes": 1000,
  "headless": true
}
```

### 获取快照
```
GET /api/calibrations/snapshots/{snapshot_id}
```

### 保存 Site Profile
```
POST /api/calibrations/site-profiles
Content-Type: application/json

{
  "snapshot_id": "uuid",
  "site": {
    "name": "example-site",
    "base_url": "https://example.com"
  },
  "page": {
    "page_id": "homepage",
    "url_pattern": "/",
    "summary": "站点首页"
  },
  "elements": [
    {
      "alias": "search.input",
      "selector": "#search",
      "description": "搜索框",
      "role": "textbox",
      "locator_strategy": "dom_path"
    }
  ]
}
```

## 目录结构

```
calibration_web_mvp/
├── app.py                      # Flask 应用主文件
├── run.py                      # 启动脚本
├── routes/                     # 路由模块
│   ├── calibration.py          # 传统视图路由
│   └── calibrations_api.py     # REST API 路由
├── services/                   # 服务模块
│   └── calibration_snapshot.py # 快照管理服务
├── utils/                      # 工具模块
│   └── calibration_serializers.py # 序列化工具
├── templates/                  # HTML 模板
│   └── calibration.html        # 主页面模板
├── static/                     # 静态资源
│   ├── css/
│   │   └── calibration.css     # 样式文件
│   └── js/
│       └── calibration.js      # 前端逻辑
├── site_profiles/drafts/       # Site Profile 草稿保存目录
├── tmp/snapshots/              # 临时快照文件目录
└── log/                        # 日志文件目录
```

## 输出格式

生成的 Site Profile 文件保存在 `site_profiles/drafts/` 目录下，格式如下：

```json
{
  "version": "2025-01-18T12:00:00+08:00",
  "site": {
    "name": "example-site",
    "base_url": "https://example.com"
  },
  "pages": [{
    "page_id": "homepage",
    "url_pattern": "/",
    "version": "2025-01-18T12:00:00+08:00",
    "generated_by": "calibration-web-mvp",
    "generated_at": "2025-01-18T12:00:00+08:00",
    "summary": "站点首页描述",
    "aliases": {
      "search.input": {
        "selector": "#search",
        "description": "搜索框",
        "role": "textbox",
        "dom_id": "dom-123",
        "locator_strategy": "dom_path"
      }
    },
    "notes": "人工标定草稿",
    "snapshot_id": "uuid"
  }]
}
```

## 调试功能

- **清理缓存**：点击右上角"清理缓存"按钮清理旧快照
- **调试信息**：点击"调试信息"按钮查看快照统计和系统状态

## 日志记录

日志文件保存在 `log/calibration-web.log`，包含：
- 页面抓取请求和结果
- DOM 树处理过程
- Site Profile 保存操作
- 系统错误和异常

## 限制说明

- 仅支持匿名可访问页面，不处理登录认证
- 单次标定仅限单个页面
- DOM 树节点数限制为 1000 个
- 页面快照每日自动清理

## 故障排除

1. **页面加载失败**：检查 URL 是否可访问，网络是否正常
2. **高亮不显示**：确保页面加载完成，刷新页面重试
3. **保存失败**：检查 `site_profiles/drafts/` 目录权限
4. **浏览器启动失败**：确保已安装 Playwright 浏览器：`playwright install chromium`

## 技术栈

- **后端**：Flask + Playwright
- **前端**：Bootstrap 5 + Vanilla JavaScript
- **数据格式**：JSON
- **日志**：Python logging