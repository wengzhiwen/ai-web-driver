# 编译器 MVP 概要设计

## 1. 背景与目标
编译器负责将 QA 的自然语言 TestRequest 转换为执行器可理解的 ActionPlan DSL。MVP 目标是实现"单用例、单流程"编译链路，验证从文本到结构化指令的可行性，并输出包含定位信息的强类型 DSL，供执行器直接消费。

## 2. 范围与非目标
- 范围：
  - 接收单个 TestRequest（Markdown格式文本步骤 + 可选元信息）。
  - 读取指定 SiteProfile（已标注元素、页面跳转关系）。
  - 通过LLM解析自然语言步骤，映射到 `goto`、`click`、`fill`、`assert` 等基础动作。
  - 产出带 Playwright selector 的 ActionPlan JSON，覆盖顺序流程与简单断言。
- 非目标：
  - 不支持多用例批量编译、循环/分支逻辑、复杂数据驱动。
  - 不处理跨页上下文推理、复杂条件判断、结果回写。
  - LLM 生成的结果基于已有 SiteProfile，不自动发现新元素。

## 3. 输入与输出
- **输入**：
  - `TestRequest`：Markdown格式文件，包含测试标题、背景、步骤列表（每步可包含参数、期望值）。
  - `SiteProfile`：JSON格式文件，包含页面列表、别名→定位器映射、页面描述等。
  - `ActionPlan Schema`：JSON Schema文件，定义输出格式规范。
- **输出**：
  ```json
  {
    "meta": {
      "testId": "RUNJPLIB-SEARCH-TSUKUBA",
      "baseUrl": "https://www.runjplib.com"
    },
    "steps": [
      {"t": "goto", "url": "/"},
      {"t": "fill", "selector": "#universitySearch", "value": "筑波大学"},
      {"t": "click", "selector": "#searchButton"},
      {"t": "assert", "selector": "ul#university-list", "kind": "visible"},
      {"t": "click", "selector": "ul#university-list"},
      {"t": "assert", "selector": "main h1, .container-fluid h1, .container h1:has-text(\"筑波大学\")", "kind": "text_contains", "value": "筑波大学"},
      {"t": "assert", "selector": "main .university-detail, .container-fluid .university-detail, .container .university-detail:has-text(\"报名截止日期\")", "kind": "text_contains", "value": "报名截止日期"}
    ]
  }
  ```

## 4. 核心流程
1. **请求解析**：解析 Markdown 格式的 TestRequest，提取测试标题、步骤列表和元信息。
2. **站点配置加载**：加载 SiteProfile JSON 文件，建立页面别名与选择器的映射关系。
3. **LLM 提示准备**：
   - 加载 ActionPlan JSON Schema 规范
   - 生成 TestRequest 和 SiteProfile 的文本摘要
   - 构建 LLM 系统提示和用户提示
4. **LLM 编译生成**：
   - 调用 LLM API 生成初始 ActionPlan JSON
   - 多轮重试机制确保输出符合 Schema 规范
   - JSON 提取和解析
5. **后处理优化**：
   - Selector 清理和标准化
   - 智能匹配 SiteProfile 中的别名
   - 文本内容断言的 `:has-text()` 语法增强
   - 补全缺失的断言参数和选择器
6. **验证与输出**：
   - Schema 合规性验证
   - Playwright 语法校验
   - 生成 testId 和完善 meta 信息
   - 输出到 `action_plans/<timestamp>/cases/<case_name>/action_plan.json`

## 5. 模块划分
- **TestRequestParser**：解析 Markdown 格式的测试需求文件。
- **SiteProfileLoader**：加载和解析站点配置 JSON 文件。
- **LLMClient**：封装 LLM API 调用，支持重试和超时机制。
- **LLMAgents**：提供提示词生成、DSL 规范说明等辅助功能。
- **LLMCompilationPipeline**：协调整个编译流程的核心引擎。
- **CLI 入口**：提供命令行接口，支持参数配置和结果输出。

## 6. 校验与错误处理
- Schema 校验：使用 JSON Schema 验证 LLM 生成的 ActionPlan 结构正确性。
- 多轮重试机制：LLM 输出不符合规范时自动重试，最多尝试指定次数。
- Playwright 语法校验：确保 selector 语法兼容，禁用不支持的伪类和 XPath。
- 完整性检查：验证必要参数（如 fill 操作的 value 值）是否缺失。
- 输出校验：最终 ActionPlan 通过完整验证流程，确保执行器能直接运行。

## 7. 运行形态
- CLI 工具：`python -m compiler_mvp.llm_cli --request test_requests/测试需求1.md --profile site_profiles/www.runjplib.com.json`
- 支持参数：
  - `--attempts`：最大重试次数（默认3次）
  - `--temperature`：LLM 温度参数（默认0.2）
  - `--api-timeout`：API 调用超时时间
  - `--plan-name`、`--case-name`：自定义输出目录名称
- 输出结构：`action_plans/<timestamp>_llm_plan/cases/<case_name>/action_plan.json`

## 8. 关键特性
- **LLM 驱动**：核心编译逻辑基于大语言模型，具备自然语言理解能力。
- **智能匹配**：通过相似度计算将 LLM 生成的选择器映射到 SiteProfile 中的标准别名。
- **文本断言增强**：自动为文本验证添加 `:has-text()` 语法，提升断言准确性。
- **上下文传递**：在多步骤操作中智能传递和复用文本参数。
- **错误自愈**：通过多轮对话机制修复 LLM 输出的格式和内容错误。

## 9. 后续扩展
- 优化 LLM 提示词策略，提升复杂场景的解析准确率。
- 增强元素发现能力，结合页面动态分析补充 SiteProfile。
- 支持条件分支、循环等复杂测试逻辑。
- 建立测试结果反馈机制，持续优化编译质量。
