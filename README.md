# ai-web-driver

## 项目整体思路

- 目标聚焦于免代码、低成本、可回放、可维护的本地化自动化测试体验，全部数据与运行均在本地完成。
- 利用标定工具对被测试对象的主要DOM和流转过程进行自然语言标定。
- 核心数据流从自然语言的测试请求出发，编译器结合站点 Profile 转为强类型的 Action Plan，执行器依据 Action Plan 顺序执行并产出 trace、报告等工件。
- 系统围绕四个协作模块构建：标定工具负责维护站点 Profile，用例编译器将需求转译为指令，测试执行器按序执行并收集证据，结果查看器整合运行明细与 Trace 供分析回溯。

## MVP 一览

### 标定工具（Profile Builder）

还没写

### 用例编译器（Compiler MVP）

已经验证

  ```bash
  python -m compiler_mvp.llm_cli \
    --request test_requests/测试需求1.md \
    --profile site_profiles/plan1_site_profile.json \
    --summary
  ```

### 测试执行器（Executor MVP）

已经验证

  ```bash
  python -m executor_mvp.cli \
    --plan-dir action_plans/plan1 \
    --summary
  ```

- 报告查看器

看情况，不一定需要MVP
