# ai-web-driver

## MVP 一览

- 标定工具（Profile Builder）：待补充
- 报告查看器：待补充
- 用例编译器（Compiler MVP）
  ```bash
  python -m compiler_mvp.llm_cli \
    --request test_requests/测试需求1.md \
    --profile site_profiles/plan1_site_profile.json \
    --summary
  ```
- 测试执行器（Executor MVP）
  ```bash
  python -m executor_mvp.cli \
    --plan-dir action_plans/plan1 \
    --summary
  ```
