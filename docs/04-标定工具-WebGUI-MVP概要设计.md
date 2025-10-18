# 标定工具 Web GUI MVP 概要设计

## 失败了
- 搞得过于复杂了，转向到尝试Chrome插件

## 1. 背景与目标
- 现有的标定 CLI MVP 已验证“页面抓取 + 自动标定草稿”链路，但缺乏人工校正与可视化能力。
- 本次 MVP 聚焦“本地 Flask + REST Web GUI”，验证手动标定的关键交互闭环：加载页面、浏览 DOM/A11y 树、选择节点联动高亮、输出 Site Profile 草稿。
- 目标是在最小实现成本下，搭建后续完整标定工具的 GUI 基石，并与既有 `profile_builder_mvp` 能力复用。

## 2. 核心验证点
- **本地 WEB GUI**：通过 Flask 提供传统视图与 REST API，前端单页完成 URL 输入、会话管理与标定操作。
- **可视化浏览器联动**：输入 URL 后，由后端启动本地有头 Chromium 窗口供用户真实交互，Web GUI 仅展示 DOM/A11y 树与标定工具。
- **DOM/A11y 联动高亮**：右侧树节点与 Chromium 窗口内的真实页面之间支持双向定位，高亮与滚动由 Playwright 会话驱动。
- **手动标定落地 Site Profile**：允许为节点填写自然语言描述/别名/定位方式，并保存为 `site_profiles/` 目录下的草稿。

## 3. 范围与非目标
- **范围**：
  - 单页面标定流程；每次操作独立于前一次。
  - 仅支持匿名可访问页面，不处理登录/鉴权。
  - Site Profile 只生成草稿版本，不涉及历史合并、版本比对。
- **非目标**：
  - 不引入自动标定/LLM。仅复用抓取与 DOM 摘要能力。
  - 不在 Web GUI 内嵌实时页面渲染，真实页面操作完全交由外部 Chromium 窗口处理。
  - 不实现跨页面导航、跳转关系、批量导出等高级功能。

## 4. 用户流程
1. 打开本地 Web GUI（Flask 渲染的入口页），右侧为 DOM/A11y 树与标定面板。
2. 在顶部输入目标 URL 并点击“启动会话”。
3. 后端借 Playwright 启动本地有头 Chromium 窗口，导航至目标页面，并返回会话 ID。
4. 用户在 Chromium 窗口内完成真实操作（滚动、点击、输入等），直至页面处于待标定状态。
5. 回到 Web GUI，点击“同步 DOM”或选择节点，右侧树结构展示当前 Playwright 页面完整的 DOM/A11y 信息。
6. 在树上选择节点，右侧表单显示该节点的可读信息，同时通过 Playwright 在 Chromium 窗口高亮对应元素。
7. 用户填写/编辑别名、描述、定位器（默认填入唯一 DOM 路径），点击“添加到标定列表”。
8. 标定列表可查看已选元素，确认后点击“保存 Site Profile”，输入站点/页面信息。
9. 后端将标定结果写入 `site_profiles/drafts/` 下的 JSON 文件，并反馈保存成功；会话可按需关闭。

## 5. 技术方案

### 5.1 整体架构
- **Flask 层**：维持 `calibration`（视图）与 `calibrations_api`（REST API）蓝图，新增“会话管理”接口族 `/api/calibrations/sessions/*`。
- **Playwright 会话管理**：
  - 新增 `services/calibration_session.py`，负责启动/复用/销毁有头 Chromium 实例，并维护 `session_id -> Playwright context/page` 的映射。
  - 每个会话包含浏览器上下文、实时 DOM 抽取能力、高亮控制与快照导出功能。
  - 通过进程内队列或 asyncio 锁保证单会话串行访问，避免 DOM 抽取时的竞争。
- **前端层**：`static/js/calibration.js` 负责会话创建、定向拉取 DOM/A11y 数据、高亮指令与标定表单交互。页面布局取消 iframe，集中展示树与表单。
- **数据缓存**：在标定过程中即时从 Playwright 抽取 DOM/A11y；若用户请求保存快照或导出，可将最新结构写入 `tmp/snapshots/<session>/<timestamp>/` 以备调试。

### 5.2 页面操控与 DOM 抽取
- `POST /api/calibrations/sessions` 接收 `{"url": "...", "viewport": {...}}` 等参数，使用 `playwright.chromium.launch(headless=False)` 打开新的可视化窗口。
- 创建会话后即时返回 `session_id`，并在后台维持 `browser_context` 与单页 `page`，供右侧面板后续调用。
- 在用户触发“同步 DOM”或选择节点时，通过以下管线获取最新结构：
  - **HTML DOM 树**：复用 CLI 的 DOM 摘要逻辑，对当前页面运行 `page.evaluate` 注入 `data-dom-id`、`data-dom-path`、计算唯一定位器。
  - **A11y 树数据**：调用 `page.accessibility.snapshot({interestingOnly: False})`，并对节点进行 `dom_id` 关联。
  - **几何信息**：借助 `page.locator(selector).bounding_box()` 或与 DOM 摘要联动，按需获取当前节点的位置信息。
- 结构数据直接通过 REST 返回给前端；必要时缓存为最近一次“抽取版本”，以便回滚或比较。

### 5.3 高亮与页面联动方案
- 右侧面板通过 REST 向后端发送 `highlight`、`scroll_into_view` 指令，由 Playwright 在当前会话页内执行对应脚本。
- 高亮实现方式：
  - 在会话初始化阶段向页面注入统一的 overlay 脚本，支持创建/移除遮罩层。
  - `highlight` 请求携带 `dom_id` 或 `selector`，后端在 Playwright 中定位节点并调用注入脚本绘制半透明框。
  - `unhighlight` 清除遮罩，避免操作后残留。
- Playwright 自带的 `page.highlight()` 与 `locator.scroll_into_view_if_needed()` 可提供基础保障，再配合自定义脚本确保视觉效果一致。
- 若页面在标定过程中发生结构变化，可再次触发 DOM 抽取，保持右侧树与实际页面同步。

### 5.4 右侧标定面板设计
- **Tab 结构**：
  - DOM 树视图：展示节点层级，展示 `tag`、`role`、`id/class/data-test`。
  - A11y 视图：针对可交互节点显示可访问性角色/名称。
- **标定表单**：
  - 自动填充：`alias`（默认 `tag.role` + 索引）、`selector`（来自 DOM path）、`role`、`description`（可编辑自然语言）。
  - 支持选择定位策略：DOM path、data-test 属性、id/class 组合，提供单选按钮切换。
  - “加入标定列表”后清空表单，待选节点标记状态。
- **状态同步**：
  - 树数据基于当前会话的最新抽取结果，并显示时间戳提醒用户必要时重新同步。
  - 当 Playwright 检测到页面导航或重大变更时，后端推送“需刷新”标记，提示前端重新获取 DOM。
- **标定列表**：
  - 列出已添加的元素，可编辑/删除。
  - 支持拖拽调序，帮助后续人工审阅。
  - 临时存储在前端状态，保存时整体提交。

### 5.5 Site Profile 草稿结构
- 复用现有 schema：
  ```json
  {
    "site": {"name": "demo", "base_url": "https://example.com"},
    "pages": [{
      "page_id": "demo_home",
      "url_pattern": "/",
      "version": "2025-01-18T12:00:00+08:00",
      "generated_by": "calibration-web-mvp",
      "summary": "示例站点的首页，包含搜索入口与热卖列表。",
      "elements": [
        {"alias": "search.input", "selector": "data-test=search-input", "role": "textbox", "description": "搜索框"}
      ],
      "notes": "人工标定草稿"
    }]
  }
  ```
- 新增字段：
  - `session_id`：记录生成标定的 Playwright 会话，便于追踪。
  - `snapshot_token`：可选，保存调用“保存快照”时生成的离线副本 ID（若用户需要固化 DOM）。
  - `a11y`：可选，保存关键 A11y 属性（如 `role`、`name`）。
  - `bounding_box`：可选，用于后续自动验证定位准确性。
- 保存逻辑完全由后端处理，前端提交 `POST /api/calibrations/site-profiles` 后由 API 负责写入文件；接口可选附带 `persist_snapshot=true`，让后端在保存 JSON 的同时落地一份 DOM/A11y 副本。
- 页面级自然语言描述（`summary` / `notes`）需由用户在保存前确认，确保导出的草稿结构与自动标定 CLI 输出保持一致。

### 5.6 REST API 设计
- `POST /api/calibrations/sessions`
  - 请求：`{"url": "...", "viewport": {"width": 1280, "height": 720}}`。
  - 行为：启动有头 Chromium，导航至 URL，返回 `session_id` 与基础状态。
- `POST /api/calibrations/sessions/<session_id>/dom-sync`
  - 请求：`{"include_bounding_box": true, "include_accessibility": true}`。
  - 返回：当前页面的 DOM 树、A11y 树、抽取时间戳。
- `POST /api/calibrations/sessions/<session_id>/highlight`
  - 请求：`{"dom_id": "...", "selector": "...", "action": "show|hide|scroll"}`，驱动页面内高亮与滚动。
- `POST /api/calibrations/sessions/<session_id>/persist-snapshot`
  - 行为：将当前页面的 DOM/A11y/HTML 写入 `tmp/snapshots/`，返回 `snapshot_token`。
- `DELETE /api/calibrations/sessions/<session_id>`
  - 关闭 Playwright 会话与浏览器窗口，释放资源。
- `POST /api/calibrations/site-profiles`
  - 请求：`{"session_id": "...", "snapshot_token": null, "site": {...}, "page": {...}, "elements": [...]}`。
  - 行为：写入 `site_profiles/drafts/<site>_<page_id>_<timestamp>.json`，必要时同时存档快照。
- 错误码扩展：增加 `SESSION_NOT_FOUND`、`SESSION_CLOSED`、`BROWSER_LAUNCH_FAILED` 等枚举，继续沿用统一响应格式。

### 5.7 组件划分与目录
- `routes/calibration.py`：渲染主页面。
- `routes/calibrations_api.py`：定义上述 REST 接口。
- `utils/calibration_serializers.py`：封装标准响应。
- `services/calibration_session.py`：负责有头浏览器会话生命周期、DOM 抽取、快照持久化。
- `utils/playwright_overlays.py`（可选）：封装注入脚本与高亮工具。
- `static/js/calibration.js`：前端主逻辑（请求 API、渲染树、高亮通信、会话状态管理）。
- `static/css/calibration.css`：布局与高亮状态样式。
- `tmp/snapshots/`：存放用户主动持久化的页面快照；每日定时清理。

## 6. MVP 完成标准
- 成功在单次 Playwright 会话内完成操作+标定，并在 `site_profiles/drafts/` 生成 JSON 草稿。
- DOM 树抽取耗时可控（目标 < 2s，节点量 ≤ 1000），选中节点时 Chromium 窗口必然高亮并滚动到可视区域。
- 浏览器启动或 DOM 抽取失败时，Web GUI 以中文提示错误并可重试/重启会话。
- 日志写入 `log/calibration-web-YYYYMMDD.log`，记录会话创建、DOM 抽取、高亮指令、保存动作与异常。

## 7. 风险与缓解
- **浏览器窗口管理复杂**：有头 Chromium 窗口可能被用户误关或遮挡。缓解：提供会话状态检测与“一键重新打开”能力。
- **会话资源泄漏**：长时间运行可能产生僵尸进程。缓解：设置空闲超时自动回收，并在 Flask 退出时统一清理。
- **多会话并发冲突**：同时标定多个页面时可能导致 DOM 数据混淆。缓解：每个会话独立 `session_id`，前端在 UI 中清晰提示当前会话，并限制并发数量。
- **A11y 树体积大**：大型页面可能导致抽取与前端渲染卡顿。缓解：限制节点数量，提供“仅展示交互元素”过滤。
- **Playwright 依赖体积**：首次启动浏览器较慢。缓解：服务启动后预热浏览器或提供加载进度提示。

## 8. 后续扩展方向
- 整合自动标定结果，与人工标定在同一界面内对比/接收建议。
- 支持多页面导航，记录跳转关系与流程边。
- 引入元素唯一性校验与截图比对，辅助人工确认。
- 与编译器输出对接，提供“引用 Site Profile 转行动作”的预览。
