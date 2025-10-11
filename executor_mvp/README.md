# Executor MVP

最小化的 ActionPlan 执行器，基于 Playwright 顺序执行单个 DSL 用例并产出运行工件。编译器阶段已将所需定位信息嵌入 DSL，执行器无需再接收 SiteProfile。

## 使用方式

目录结构示例：
```
action_plans/plan1/
  cases/
    tsukuba_search/
      action_plan.json
```

运行命令：
```bash
export RUN_ENV_FILE=.env  # 可选，若需要自定义环境变量
python -m executor_mvp.cli \
  --plan-dir action_plans/plan1 \
  --case tsukuba_search \
  --output results \
  --summary
```

参数说明：
- `--plan-dir`：包含 `cases/` 目录的执行计划根目录。
- `--case`：`cases/` 下的子目录名；若仅有一个用例可省略。
- `--headed`：运行时打开浏览器窗口，默认 headless。
- `--screenshots`：`none`、`on-failure`、`all`。
- `--timeout`：步骤默认超时时间（毫秒）。
- `--summary`：执行完打印 `run.json` 内容。

执行后将生成：
```
results/
  20241011T123000Z_RUNJP-SEARCH-TSUKUBA-001/
    run.json
    runner.log
    steps/
      01.png
      02.png
```

## 依赖

- `playwright`
- `python-dotenv`（可选，用于加载 `.env`）

首次执行前请确保运行过 `playwright install` 以安装浏览器内核。
