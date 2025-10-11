# 执行器 MVP 概要设计

## 1. 背景与目标
执行器负责按 ActionPlan DSL 驱动 Playwright 完成端到端 UI 测试。MVP 以“单用例顺序执行 + 基础结果落地”为目标，验证总体链路可行性，并为后续增强（失败取证、批量运行、数据驱动）奠定结构。

## 2. 范围与非目标
- 范围：加载单个 ActionPlan JSON；串行执行步骤；记录状态、日志与基本截图；输出最小运行报告。
- 非目标：数据表驱动、多用例编排、断点续跑、重试策略、Trace/网络/DOM 取证、权限控制、浏览器复用。

## 3. 前置条件与假设
- 运行环境已安装 Playwright Python 版及浏览器依赖。
- ActionPlan DSL 由上游编译器生成并通过基础 Schema 校验。
- SiteProfile 已确保别名定位器可用；执行器只做最小验证。

## 4. 理想流程
1. 读取并解析 ActionPlan JSON（支持文件路径或内存对象）。
2. 进行核心字段校验，确保 `meta` 与 `steps` 完整。
3. 初始化 Playwright：启动浏览器、创建 context/page。
4. 以顺序方式调度步骤：
   - `goto`：拼接 `meta.baseUrl` 与目标 URL。
   - `fill`/`click`：基于别名定位器操作元素。
   - `assert`：支持 `visible`、`text_equals`、`attr_equals` 等基础断言。
5. 逐步记录执行结果（成功/失败、耗时、异常信息）。
6. 根据策略截取截图（默认失败时截取，选项支持全量）。
7. 汇总输出 RunReport JSON，写入结果目录；关闭 Playwright 资源。

## 5. 组件划分
- **RunnerEntry**：公开 `run_action_plan(plan: dict | str)`；组织整体流程。
- **PlanValidator**：基于 JSON Schema 做字段级校验，并验证 alias/URL 的基本合法性。
- **StepDispatcher**：将 DSL 步骤映射至具体 Playwright 调用，封装异常。
- **ResultReporter**：维护运行状态、写入步骤日志、生成截图、输出报告 JSON。
- **IOAdapter**：生成结果目录结构，例如 `results/<timestamp>/`，包含 `run.json`、`steps/<index>.png`、`runner.log`。

## 6. 接口与数据结构
- **输入**：
  ```json
  {
    "meta": {"testId": "TC-001", "baseUrl": "https://app.example"},
    "steps": [
      {"t": "goto", "url": "/login"},
      {"t": "fill", "alias": "login.email", "value": "qa@example.com"},
      {"t": "click", "alias": "login.submit"},
      {"t": "assert", "kind": "visible", "alias": "home.banner"}
    ]
  }
  ```
- **输出** (`run.json` 示例)：
  ```json
  {
    "run_id": "2024-05-01T10-30-00Z_TC-001",
    "status": "failed",
    "test_id": "TC-001",
    "started_at": "2024-05-01T10:30:00Z",
    "finished_at": "2024-05-01T10:30:18Z",
    "steps": [
      {"index": 1, "t": "goto", "status": "passed"},
      {"index": 2, "t": "fill", "status": "passed"},
      {"index": 3, "t": "click", "status": "failed", "error": "TimeoutError...", "screenshot": "steps/3.png"}
    ],
    "artifacts_dir": "results/2024-05-01T10-30-00Z"
  }
  ```

## 7. 错误处理策略
- 任一步骤抛出异常：记录失败、保存截图（若启用）、终止后续步骤。
- 保证浏览器关闭与资源释放（`try/finally`）。
- 异常消息统一封装为人类可读描述，附加 Playwright 原始异常用于调试。

## 8. 可观测性
- 运行日志写入 `runner.log`，记录关键事件（启动、每步操作、异常）。
- 支持设置日志等级，默认 info，调试场景可切换为 debug。
- RunReport JSON 作为后续报告查看器的数据源。

## 9. 风险与后续扩展点
- 定位器失效仅能通过失败截图定位，建议在后续版本补充 DOM 片段/近似候选。
- 长时间执行的浏览器会话可能泄露状态；未来可增加 context 复用控制。
- 结果目录可能快速膨胀，需后续加入清理策略与压缩归档。

## 10. 建议
1. 尽快固化 ActionPlan JSON Schema，减少运行期异常。
2. 构建包含静态 demo 页面的最小集成测试，确保链路稳定。
3. 预留 ResultReporter 扩展接口，为 trace、网络日志等后续工件接入留余地。
