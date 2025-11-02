# 执行器 MVP 概要设计

## 1. 背景与目标
执行器负责按 ActionPlan DSL 驱动 Playwright 完成端到端 UI 测试。MVP 以"单用例顺序执行 + 基础结果落地"为目标，验证总体链路可行性。

**已完成升级**：
- ✅ 批量执行：支持随机抽样和全量执行
- ✅ JavaScript时序优化：解决事件绑定竞态问题
- ✅ 统一结果目录：单个和批量执行使用相同结构
- ✅ 简单报告生成：不依赖LLM的快速报告
- ✅ 灵活测试用例加载：支持多种指定方式

## 2. 范围与非目标
- 范围：
  - 加载单个或多个 ActionPlan JSON
  - 串行执行步骤
  - 记录状态、日志与基本截图
  - 输出结构化运行报告
  - 提供 CLI 接口
  - **新增**：批量执行多个测试用例
  - **新增**：随机抽样测试用例
  - **新增**：统一的批次结果目录和报告
- 非目标：断点续跑、重试策略、Trace/网络/DOM 取证、权限控制、浏览器复用、并行执行。

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
- **Executor**：核心执行引擎，负责整体流程编排和 Playwright 生命周期管理
  - 支持外部指定artifacts_dir，便于统一结果目录结构
  - click操作添加200ms等待，解决JavaScript事件绑定时序问题
  - click失败时自动重试1次（间隔500ms），提升稳定性
- **ExecutorSettings**：运行时配置管理，支持 headed 模式、超时设置、截图策略等
- **PlanLoader**：负责从目录结构加载和解析 ActionPlan JSON
  - 支持多种格式：目录中的action_plan.json、直接的.json文件
  - 智能匹配：目录名、文件名（带/不带.json）、文件名模式
  - 灵活的case指定方式，提升调试效率
- **数据模型**（ActionPlan、ActionStep、StepResult、RunResult）：结构化数据定义，支持完整的执行状态记录
- **BatchExecutor**：批量执行协调器
  - 测试用例发现和加载
  - 随机抽样支持（可指定随机种子）
  - 批量串行执行
  - 直接创建统一的case子目录
- **BatchResult**：批量执行结果模型，包含总体统计和各用例结果
- **SimpleReportGenerator**：简单报告生成器（不依赖LLM）
  - 总体统计（包括执行时长）
  - 未通过用例详情（case id、结果目录、时长、失败步骤、错误）
  - 通过用例详情（时长、通过步骤）
  - Case ID可直接复制粘贴用于单独执行
- **CLI接口**：提供命令行入口
  - 支持单个/批量执行模式自动切换
  - 统一的结果目录结构（单个和批量）
  - 简洁实用的输出格式

## 6. 接口与数据结构

### 输入接口

#### 单个用例执行
```bash
python -m executor_mvp.cli \
  --plan-dir action_plans/<timestamp>_llm_plan \
  [--case <case-name>] \
  [--headed] \
  [--screenshots none|on-failure|all] \
  [--timeout <ms>] \
  [--summary]
```

#### 批量执行（新增）
```bash
python -m executor_mvp.cli \
  --plan-dir action_plans/<timestamp>_data_driven_plan \
  --batch <count> \
  [--random-seed <seed>] \
  [--headed] \
  [--screenshots none|on-failure|all] \
  [--timeout <ms>] \
  [--no-report] \
  [--summary]
```

**批量执行参数说明**：
- `--batch <count>`：批量执行模式，指定运行的测试用例数量（0 表示运行全部）
- `--random-seed <seed>`：随机种子，用于可重现的随机选择

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

### 单个用例输出结构（run.json）
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

### 统一的结果目录结构

**所有执行模式**（单个或批量）都使用相同的目录结构：

```
results/<时间戳>_[batch_]run/
├── test_report.md                  # 测试报告（简单格式，不依赖LLM）
├── batch_summary.json              # 批量执行摘要（批量模式）
├── <case_name_1>/                  # 测试用例 1 结果
│   ├── run.json                    # 用例执行详情
│   ├── runner.log                  # 用例执行日志
│   └── steps/                      # 步骤截图
│       ├── 04.png
│       └── ...
├── <case_name_2>/                  # 测试用例 2 结果
│   ├── run.json
│   ├── runner.log
│   └── steps/
└── ...
```

**示例**：
```
# 单个case执行
results/20251103T003445Z_run/
├── test_report.md
└── case_002/
    ├── run.json
    ├── runner.log
    └── steps/

# 批量执行
results/20251102T163823Z_batch_run/
├── test_report.md
├── batch_summary.json
├── case_013_20251102T155633Z/
├── case_058_20251102T155633Z/
└── ...
```

#### batch_summary.json
```json
{
  "batch_id": "20251102T151750Z_batch_run",
  "total_cases": 10,
  "passed_cases": 8,
  "failed_cases": 2,
  "error_cases": 0,
  "success_rate": 80.0,
  "started_at": "2025-11-02T15:17:50.668338",
  "finished_at": "2025-11-02T15:18:32.630910",
  "cases": [
    {
      "test_id": "SHOP-EXISTENCE-AND-DISPLAY-001_075",
      "status": "failed",
      "steps_passed": 3,
      "steps_total": 4,
      "artifacts_dir": "results/20251102T151750Z_batch_run/au_shop_test_075"
    }
  ]
}
```

#### test_report.md
自动生成的简单测试报告（不依赖LLM），包含：

```markdown
# 测试执行报告

**批次ID**: `20251102T163823Z_batch_run`  
**执行时间**: 2025-11-02 16:38:23 - 2025-11-02 16:39:39  
**总时长**: 76.32秒  

## 📊 总体统计
| 指标 | 数值 |
|------|------|
| 总测试用例数 | 5 |
| ✅ 通过 | 1 |
| ❌ 失败 | 4 |
| 成功率 | 20.0% |
| 总执行时长 | 76.32秒 |
| 平均每用例时长 | 15.26秒 |

## ❌ 未通过的用例
| Case ID | 结果目录 | 执行时长 | 通过步骤 | 失败步骤 | 错误信息 |
|---------|----------|----------|----------|----------|----------|
| `case_328_20251102T155633Z` | `results/...` | 17.21秒 | 3/4 | 步骤4 | ... |

## ✅ 通过的用例
| Case ID | 执行时长 | 通过步骤 |
|---------|----------|----------|
| `case_013_20251102T155633Z` | 3.20秒 | 16/16 |
```

**特点**：
- Case ID可直接复制粘贴到`--case`参数
- 包含所有必要的诊断信息
- 生成速度快（秒级）

## 7. 错误处理策略
- 任一步骤抛出异常：记录失败、保存截图（若启用）、终止后续步骤
- 保证浏览器关闭与资源释放（`try/finally`）
- 异常消息统一封装为用户友好的中文描述，避免技术细节干扰
- Playwright TimeoutError 转译为"验证失败：未能找到指定的DOM元素"等用户可理解的提示
- 错误信息记录在步骤级别，不影响整体运行报告结构
- **新增**：click操作失败时自动重试1次
  - 首次失败后等待500ms
  - 重新执行click操作
  - 重试成功也算通过
  - 提升对JavaScript时序问题的容错能力

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
- **完整的数据模型体系**：定义了 ActionStep、ActionPlan、StepResult、RunResult 等核心数据结构，支持完整的执行状态跟踪和结果序列化
- **灵活的加载机制**：支持从目录结构自动发现和加载测试用例
  - 支持多种格式：目录/action_plan.json、直接.json文件
  - 智能匹配：目录名、文件名、文件名模式
  - 便于调试和批量执行
- **强大的执行引擎**：基于 Playwright 的稳定执行引擎
  - 页面导航、元素操作、断言验证等完整功能
  - **JavaScript时序优化**：click后添加200ms等待
  - **自动重试机制**：click失败时自动重试1次
  - 彻底解决JavaScript事件绑定的竞态问题
- **智能错误处理**：将技术异常转换为用户友好的中文提示
  - 特别针对定位器超时等常见场景
  - click重试失败时提供详细的错误信息
- **多策略截图**：支持 none、on-failure、all 三种截图模式，为失败取证提供完整支持
- **完善的CLI接口**：提供丰富的命令行参数
  - 支持 headed 模式、超时控制、输出目录等灵活配置
  - 支持单个和批量执行模式
  - 支持随机抽样和随机种子
- **全面的上下文收集**：自动记录页面 URL、标题、DOM 大小等上下文信息，便于问题诊断
- **简单报告生成**：不依赖LLM的快速报告生成器
  - 总体统计（执行时长、成功率）
  - 未通过用例详情（case id、结果目录、时长、失败步骤）
  - 通过用例详情（时长、通过步骤）
  - Case ID可直接复制粘贴执行
  - 生成速度快（秒级）
- **统一结果结构**：单个和批量执行使用完全相同的目录结构，降低理解成本

## 12. 测试报告生成系统

### 12.1 简单报告生成器（默认）

**设计目标**：提供快速、简洁、实用的测试报告，不依赖外部API

**核心功能**：
- 总体统计：测试用例数、通过/失败数、成功率、执行时长
- 未通过用例详情：case id、结果目录、时长、失败步骤、错误信息
- 通过用例详情：case id、执行时长、通过步骤数
- Case ID格式优化：可直接复制粘贴到`--case`参数

**技术特点**：
- 纯Python数据处理，无需LLM
- 生成速度快（秒级）
- 格式统一，易于解析
- 包含所有必要的诊断信息

**模块**：`executor_mvp/simple_report_generator.py`

### 12.2 LLM报告生成器（可选）

**设计目标**：为单个测试用例提供详细的、人类可读的测试分析报告

**核心功能**：
- 智能分析测试目标、页面流程、关键操作
- 详细验证点列示（选择器、验证类型、预期结果）
- 性能指标计算和分析
- 专业的结论和建议

**启用方式**：
- 单个case执行时默认启用
- 可通过 `--no-report` 参数禁用
- 批量执行时自动禁用（使用简单报告生成器）

**技术特性**：
- LLM调用失败时自动降级
- 报告保存至 `test_report.md`（与简单报告同名，批量时被简单报告替代）

**模块**：`executor_mvp/report_generator.py`

### 12.3 报告选择策略

| 执行模式 | 报告生成器 | 原因 |
|---------|-----------|------|
| 单个case | LLM报告（可禁用） | 详细分析单个用例 |
| 批量执行 | 简单报告 | 快速汇总多个用例 |
| 统一输出 | test_report.md | 统一的文件名

## 12. 联调成果与验证
- 与标定工具和编译器完成端到端联调，形成完整的测试自动化链路。
- 支持从 ActionPlan 目录结构直接加载测试用例，与编译器输出格式完全兼容。
- 通过实际测试验证了 goto、fill、click、assert 等核心功能的稳定性。
- 截图和日志机制为问题定位提供了有效支撑。
- CLI 工具具备生产可用性，支持灵活的参数配置和结果查看。
- 错误处理机制经过联调验证，能够提供清晰的故障诊断信息。