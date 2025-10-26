# 执行器 MVP 概要设计

## 1. 背景与目标
执行器负责按 ActionPlan DSL 驱动 Playwright 完成端到端 UI 测试。MVP 以"单用例顺序执行 + 基础结果落地"为目标，验证总体链路可行性，并为后续增强（失败取证、批量运行、数据驱动）奠定结构。

## 2. 范围与非目标
- 范围：加载单个 ActionPlan JSON；串行执行步骤；记录状态、日志与基本截图；输出结构化运行报告；提供 CLI 接口。
- 非目标：数据表驱动、多用例编排、断点续跑、重试策略、Trace/网络/DOM 取证、权限控制、浏览器复用。

## 3. 前置条件与假设
- 运行环境已安装 Playwright Python 版及浏览器依赖。
- ActionPlan DSL 由上游编译器生成并通过基础 Schema 校验。
- ActionPlan DSL 已携带可直接使用的 selector；执行器不再加载 SiteProfile。
- 测试用例按目录结构组织：`<plan-dir>/cases/<case-name>/action_plan.json`。

## 4. 理想流程
1. 通过 CLI 读取并解析 ActionPlan JSON，支持目录结构和用例选择。
2. 进行核心字段校验，确保 `meta` 与 `steps` 完整且格式正确。
3. 初始化 Playwright：启动浏览器、创建 context/page，支持 headed/headless 模式。
4. 以顺序方式调度步骤：
   - `goto`：拼接 `meta.baseUrl` 与目标 URL。
   - `fill`/`click`：基于步骤内提供的 selector 操作元素。
   - `assert`：支持 `visible`、`text_contains`、`text_equals` 等基础断言。
5. 逐步记录执行结果（成功/失败、耗时、页面上下文信息）。
6. 根据策略截取截图（`none`、`on-failure`、`all`），默认失败时截取。
7. 汇总输出 RunReport JSON，写入结果目录；关闭 Playwright 资源。
8. 可选输出执行摘要到标准输出。

## 5. 组件划分
- **Executor**：核心执行引擎，负责整体流程编排和 Playwright 生命周期管理。
- **ExecutorSettings**：运行时配置管理，支持 headed 模式、超时设置、截图策略等。
- **PlanLoader**：负责从目录结构加载和解析 ActionPlan JSON，支持多用例场景。
- **数据模型**（ActionPlan、ActionStep、StepResult、RunResult）：结构化数据定义，支持完整的执行状态记录。
- **CLI接口**：提供命令行入口，支持参数配置和结果摘要输出。

## 6. 接口与数据结构

### 输入接口
```bash
python -m executor_mvp.cli \
  --plan-dir action_plans/<timestamp>_llm_plan \
  [--case <case-name>] \
  [--headed] \
  [--screenshots none|on-failure|all] \
  [--timeout <ms>] \
  [--summary]
```

### ActionPlan DSL 结构
```json
{
  "meta": {
    "testId": "RUNJPLIB-SEARCH-TSUKUBA",
    "baseUrl": "https://www.runjplib.com/"
  },
  "steps": [
    {"t": "goto", "url": "/"},
    {"t": "fill", "selector": "input[name='q']", "value": "筑波大学"},
    {"t": "click", "selector": "button[type='submit']"},
    {"t": "assert", "kind": "visible", "selector": ".search-results"}
  ]
}
```

### 输出结构（run.json）
```json
{
  "run_id": "20251012T130117Z_RUNJPLIB-SEARCH-TSUKUBA",
  "test_id": "RUNJPLIB-SEARCH-TSUKUBA",
  "status": "failed",
  "started_at": "2025-10-12T13:01:17.000Z",
  "finished_at": "2025-10-12T13:01:25.000Z",
  "steps": [
    {
      "index": 1,
      "t": "goto",
      "status": "passed",
      "started_at": "2025-10-12T13:01:17.000Z",
      "finished_at": "2025-10-12T13:01:19.000Z"
    },
    {
      "index": 7,
      "t": "assert",
      "selector": ".university-detail",
      "status": "failed",
      "error": "验证失败：未能找到指定的DOM元素",
      "screenshot": "steps/07.png",
      "current_url": "https://www.runjplib.com/search?q=筑波大学",
      "page_title": "搜索结果",
      "dom_size_bytes": 42342
    }
  ],
  "artifacts_dir": "results/20251012T130117Z_RUNJPLIB-SEARCH-TSUKUBA"
}
```

## 7. 错误处理策略
- 任一步骤抛出异常：记录失败、保存截图（若启用）、终止后续步骤。
- 保证浏览器关闭与资源释放（`try/finally`）。
- 异常消息统一封装为用户友好的中文描述，避免技术细节干扰。
- Playwright TimeoutError 转译为"验证失败：未能找到指定的DOM元素"等用户可理解的提示。
- 错误信息记录在步骤级别，不影响整体运行报告结构。

## 8. 可观测性
- 运行日志写入 `runner.log`，记录关键事件（启动、每步操作、异常）。
- 支持 CLI 参数控制日志等级和输出详细程度。
- 结构化的 RunReport JSON 作为后续报告查看器的数据源。
- 截图支持失败取证和全量记录两种模式。
- 页面上下文信息（URL、标题、DOM大小）记录在步骤结果中。

## 9. 运行时配置
- **浏览器模式**：支持 headed/headless 切换。
- **超时控制**：全局默认超时设置（毫秒）。
- **截图策略**：none、on-failure（默认）、all 三种模式。
- **输出目录**：可配置结果存储位置。
- **环境变量**：支持通过 .env 文件加载配置。

## 10. 风险与后续扩展点
- 定位器失效仅能通过失败截图定位，建议在后续版本补充 DOM 片段/近似候选。
- 长时间执行的浏览器会话可能泄露状态；未来可增加 context 复用控制。
- 结果目录可能快速膨胀，需后续加入清理策略与压缩归档。
- 当前仅支持单用例执行，后续可扩展批量执行和并行处理能力。
- 错误处理可进一步细化，区分不同类型的失败原因。

## 11. 核心实现特性
- **完整的数据模型体系**：定义了 ActionStep、ActionPlan、StepResult、RunResult 等核心数据结构，支持完整的执行状态跟踪和结果序列化。
- **灵活的加载机制**：支持从目录结构自动发现和加载测试用例，兼容编译器输出的标准格式。
- **强大的执行引擎**：基于 Playwright 的稳定执行引擎，支持页面导航、元素操作、断言验证等完整功能。
- **智能错误处理**：将技术异常转换为用户友好的中文提示，特别是针对定位器超时等常见场景。
- **多策略截图**：支持 none、on-failure、all 三种截图模式，为失败取证提供完整支持。
- **完善的CLI接口**：提供丰富的命令行参数，支持 headed 模式、超时控制、输出目录等灵活配置。
- **全面的上下文收集**：自动记录页面 URL、标题、DOM 大小等上下文信息，便于问题诊断。
- **LLM驱动测试报告生成**：集成智能报告生成器，基于执行结果自动生成专业的人类可读测试报告，包含详细验证点清单和性能分析。
- **详细验证点列示**：报告完整列出所有验证检查点，包括具体选择器、验证类型和预期结果，大幅提升测试透明度。

## 12. 测试报告生成系统

### 12.1 设计目标
为执行器提供智能化的测试报告生成能力，让测试负责人能够快速、准确地了解测试执行结果和系统质量状况。

### 12.2 核心功能
- **智能分析引擎**：基于 ActionPlan 和 RunResult 自动分析测试目标、页面流程、关键操作和验证点
- **详细验证点列示**：完整列出所有验证检查点，包括选择器、验证类型、预期内容和执行结果
- **性能指标计算**：自动计算执行时间、成功率、平均步骤耗时等关键性能指标
- **人性化报告生成**：使用 LLM 生成专业但易懂的测试报告，语气积极但客观

### 12.3 报告内容结构
1. **测试概览**：基本信息、执行状态、成功率、执行时间
2. **测试目标**：自动推断的测试目标和验证范围
3. **测试流程**：页面访问路径和关键操作统计
4. **详细验证点**：所有验证点的完整清单和结果说明
5. **执行摘要**：关键成就、性能指标、失败分析
6. **结论与建议**：专业的测试结论和后续建议

### 12.4 技术特性
- **容错机制**：LLM 调用失败时自动降级到模板报告
- **灵活配置**：支持通过 `--no-report` 参数禁用报告生成
- **实时显示**：执行完成后立即显示报告摘要
- **标准化输出**：Markdown 格式，便于阅读和分享

### 12.5 集成方式
- 执行器设置中新增 `generate_report` 配置项
- 执行完成后自动调用报告生成器
- 报告文件保存至结果目录的 `test_report.md`
- CLI 自动显示报告摘要，提升用户体验

## 12. 联调成果与验证
- 与标定工具和编译器完成端到端联调，形成完整的测试自动化链路。
- 支持从 ActionPlan 目录结构直接加载测试用例，与编译器输出格式完全兼容。
- 通过实际测试验证了 goto、fill、click、assert 等核心功能的稳定性。
- 截图和日志机制为问题定位提供了有效支撑。
- CLI 工具具备生产可用性，支持灵活的参数配置和结果查看。
- 错误处理机制经过联调验证，能够提供清晰的故障诊断信息。