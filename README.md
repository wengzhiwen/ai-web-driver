# ai-web-driver

## 项目整体思路

- 目标聚焦于免代码、低成本、可回放、可维护的本地化自动化测试体验，全部数据与运行均在本地完成。
- 利用标定工具对被测试对象的主要DOM和流转过程进行自然语言标定。
- 核心数据流从自然语言的测试请求出发，编译器结合站点 Profile 转为强类型的 Action Plan，执行器依据 Action Plan 顺序执行并产出 trace、报告等工件。
- 系统围绕四个协作模块构建：标定工具负责维护站点 Profile，用例编译器将需求转译为指令，测试执行器按序执行并收集证据，结果查看器整合运行明细与 Trace 供分析回溯。

## MVP 一览

### 标定工具（Profile Builder）

- Chrome 插件 MVP（`calibration-chrome-extension/`）
  - Alt+P 进入标注模式，悬停高亮并点击采集元素，侧边面板可浏览 DOM 树、编辑标注备注。
  - 每个标注项自动采集标准化 URL、元素指纹、候选选择器、`cssPath`、位置信息等字段，并存储在 `chrome.storage.local`。
  - 支持按照 Frame 切换、智能节点过滤与搜索，导出符合 `site_profiles` 标准的 JSON，开箱即用地对接执行器。

- CLI 自动标定草稿可针对单个 URL 生成 Site Profile 片段并合并：

```bash
python -m profile_builder_mvp.cli \
  --url https://example.com/products \
  --append-to site_profiles/shop.json
```
- 如果未指定 `--append-to` 或 `--output`，结果会写入 `site_profiles/<时间戳>/<域名-路径>.json`，避免覆盖历史草稿。
- 执行过程中会询问页面是否为详情页，并自动将页面名称抽象为如“博客详情页”
- 传入 `--interactive` 可在抓取后逐步裁剪长文本、采样重复结构

### 用例编译器（Compiler MVP）

已经验证

  ```bash
  python -m compiler_mvp.llm_cli \
    --request test_requests/测试需求1.md \
    --profile site_profiles/plan1_site_profile.json \
    --summary
  ```
- 结果会保存到 `action_plans/` 目录中

### 测试执行器（Executor MVP）

已经验证

  ```bash
  python -m executor_mvp.cli \
    --plan-dir action_plans/plan1 \
    --summary
  ```
- 结果会写入到 `results/` 目录中

### 自然语言测试（NL Driven Testing MVP）

- 将 Markdown/文本测试说明交给 `NL_driven_test_agent/run.py`，由 Claude Code CLI 驱动 Playwright MCP 执行，并生成 Markdown 报告与截图。
- 工件统一归档到 `test_reports/` 目录，报告包含步骤、断言、错误、截图等信息。
- 示例：

  ```bash
  python NL_driven_test_agent/run.py test_requests/筑波大学报名查询.md
  ```

### 报告查看器

看情况，不一定需要MVP
