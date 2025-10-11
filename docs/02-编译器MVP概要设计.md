# 编译器 MVP 概要设计

## 1. 背景与目标
编译器负责将 QA 的自然语言 TestRequest 转换为执行器可理解的 ActionPlan DSL。MVP 目标是实现“单用例、单流程”编译链路，验证从文本到结构化指令的可行性，并输出包含定位信息的强类型 DSL，供执行器直接消费。

## 2. 范围与非目标
- 范围：
  - 接收单个 TestRequest（文本步骤 + 可选元信息）。
  - 读取指定 SiteProfile（已标注元素、跳转关系）。
  - 解析每条自然语言步骤，映射到 `goto`、`click`、`fill`、`assert` 等基础动作。
  - 产出带 Playwright selector 的 ActionPlan JSON，覆盖顺序流程与简单断言。
- 非目标：
  - 不支持多用例批量编译、循环/分支逻辑、复杂数据驱动。
  - 不接入 LLM 自动生成；优先使用规则/模板，LLM 仅作为可选辅助。
  - 不处理跨页上下文推理、复杂条件判断、结果回写。

## 3. 输入与输出
- **输入**：
  - `TestRequest`：名称、业务背景、自然语言步骤列表（每步可包含参数、期望值）。
  - `SiteProfile`：页面列表、别名→定位器映射、页面跳转关系（编译器内部缓存，执行器不直接依赖）。
- **输出**：
  ```json
  {
    "meta": {
      "testId": "RUNJP-SEARCH-TSUKUBA-001",
      "baseUrl": "https://www.runjplib.com"
    },
    "steps": [
      {"t": "goto", "url": "/"},
      {"t": "fill", "selector": "input#universitySearch", "value": "筑波大学"},
      {"t": "click", "selector": "button#searchButton"},
      {"t": "assert", "kind": "text_contains", "selector": "main h2:has-text('报名截止日期')", "value": "报名截止日期"}
    ]
  }
  ```

## 4. 核心流程
1. **预处理**：清洗 TestRequest（去除编号、统一量词），加载 SiteProfile 到内存索引。
2. **步骤解析**：将自然语言拆解为“动作 + 目标 + 参数”三元组。
3. **元素解析**：根据文字描述在 SiteProfile 中查找候选元素，选择优先匹配（别名、页面上下文）。
4. **命令生成**：映射为 DSL 步骤（含 selector/url/value/kind）。
5. **验证与补全**：
   - 确保 selector 存在。
   - URL 合法、断言类型受支持。
   - 补全 `meta` 字段（testId/baseUrl）。
6. **输出**：以 JSON 写入 `cases/<name>/action_plan.json`。

## 5. 模块划分
- **RequestLoader**：读取 TestRequest（JSON/Markdown），输出标准结构体。
- **ProfileResolver**：解析 SiteProfile，提供别名查询、页面跳转辅助。
- **NLStepParser**：将文本步骤拆成动作语义（规则/模板 + 关键字表）。
- **ActionSynthesizer**：结合解析结果与 Profile 选出 selector，生成 DSL step。
- **PlanAssembler**：聚合 meta/steps，序列化输出，并记录编译日志。

## 6. 校验与错误处理
- Schema 校验：输入 TestRequest/SiteProfile 结构正确。
- 步骤合法性：未识别动作或缺少元素 → 返回错误报告并终止。
- 多候选冲突：返回候选列表给用户人工确认（MVP 输出警告即可）。
- 输出校验：生成的 ActionPlan 通过 JSON Schema 验证，确保执行器能直接运行。

## 7. 运行形态
- 提供 CLI：`python -m compiler_mvp.cli --request docs/cases/tsukuba.md --profile site_profiles/runjp.json --output action_plans/plan1/cases/tsukuba_search/action_plan.json`
- 可选启用 LLM 辅助：配置环境变量启用；默认关闭。

## 8. 后续扩展
- 引入 LLM/NLU 提升复杂句解析能力，支持条件/循环。
- 结合历史运行数据，自动推荐元素映射或发现 SiteProfile 漏项。
- 输出多级断言、接口校验、数据驱动（占位符 + 数据表）。
- 建立交互式 UI，支持人工确认与修订。
