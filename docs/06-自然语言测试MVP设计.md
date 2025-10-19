# 06-完全自然语言测试用例驱动的研发测试MVP设计文档

## 概述

本MVP实现了一个完全基于自然语言的自动化测试框架，用户可以通过编写Markdown格式的测试用例，自动驱动Playwright MCP进行浏览器测试，并利用Claude Code进行智能断言和测试报告生成。

## 核心特性

1. **自然语言测试说明**：直接读取文本/Markdown测试需求，将内容原样交给Claude
2. **Playwright MCP集成**：通过Claude Code CLI驱动Playwright MCP执行浏览器操作
3. **断言回传复用**：复用Claude返回的断言结果，失败信息会写入报告
4. **自动报告生成**：生成Markdown测试报告，展示步骤、错误与截图
5. **工件统一归档**：测试截图与报告自动汇总到`test_reports`目录

## 系统架构

```
┌──────────────────┐    ┌────────────────────┐    ┌────────────────────┐
│   自然语言用例   │───▶│ NL Driven Test CLI │───▶│   Claude Code CLI   │
└──────────────────┘    └────────────────────┘    └────────────────────┘
                                                              │
                                                              ▼
                                                ┌────────────────────────┐
                                                │  Playwright MCP 执行层 │
                                                └────────────────────────┘
                                                              │
                                                              ▼
                                                ┌────────────────────────┐
                                                │   测试报告 & 截图归档   │
                                                └────────────────────────┘
```

## 组件设计

### 1. 测试需求文件

目前对文件格式不做强制要求；推荐使用Markdown描述测试背景、步骤与断言，内容会原样注入Claude Prompt。

### 2. NL驱动测试代理 (`NL_driven_test_agent/run.py`)

- 读取测试需求文件
- 构建测试执行Prompt并调用`claude` CLI
- 解析Claude返回的JSON结果
- 生成Markdown测试报告并输出到`./test_reports/`

### 3. Playwright MCP执行

通过Claude Code CLI的MCP插件完成：

- 页面导航
- 元素操作
- 截图采集
- 错误上报

### 4. 全局工件管理

- 截图默认保存在`.playwright-mcp`目录
- `run.py`在后处理中把截图集中搬迁到`./test_reports/`
- 报告内记录搬迁后的最终路径

### 5. 测试报告内容

- 基础信息：执行时间、文件名、耗时
- 测试总结：Claude返回的整体结论
- 执行步骤：Claude返回的`steps_executed`
- 断言结果：`assertions_verified`列表
- 错误信息：`errors`列表
- 测试截图：搬迁后的截图路径

## 工作流程

1. **输入阶段**：读取自然语言测试说明并拼装执行Prompt
2. **执行阶段**：通过Claude Code CLI驱动Playwright MCP执行测试
3. **验证阶段**：复用Claude输出的断言与错误信息
4. **报告阶段**：生成Markdown报告并统一搬迁截图

## 技术栈

- **核心语言**：Python 3.8+
- **自动化**：Claude Code CLI + Playwright MCP
- **日志与报告**：Python `logging` 与 Markdown生成
- **依赖管理**：`requirements.txt`

## 使用示例

### 创建测试用例

```markdown
# 测试用例：筑波大学报名信息查询

## 测试目标
验证runjplib.com网站上筑波大学的报名截止日期信息是否正确显示

## 测试步骤
1. 打开runjplib.com网站
2. 在页面中找到筑波大学的链接
3. 点击筑波大学链接进入详情页面
4. 在详情页面中查找报名截止日期信息

## 预期结果
页面应该显示筑波大学的详细报名信息，包含明确的截止日期

## 断言条件
- 页面标题包含"筑波大学"
- 页面包含"报名截止日期"相关信息
- 显示的日期格式为"YYYY年MM月DD日"

## 测试数据
- 目标URL: https://runjplib.com
- 备用URL: https://www.runjplib.com
```

### 执行测试

```bash
python NL_driven_test_agent/run.py test_requests/筑波大学报名查询.md
```

### 生成的报告

测试完成后将生成Markdown报告，包含：
- 测试执行时间线
- 每步操作的截图
- 断言结果详情
- 问题分析和建议
- 与测试报告同目录保存的原始截图

## 配置文件

config.yaml：
```yaml
# Claude Code配置
claude_code:
  model: "claude-3-5-sonnet-20241022"
  timeout: 300
  max_retries: 3

# Playwright MCP配置
playwright:
  browser: "chromium"
  headless: false
  viewport:
    width: 1920
    height: 1080
  timeout: 30000

# 测试配置
test:
  screenshot_step: true
  video_record: false
  retry_failed: true
  report_format: "html"
  output_dir: "./test_reports"
```

## 扩展性设计

1. **多步骤复杂测试**：支持条件分支和循环
2. **数据驱动测试**：支持测试数据文件
3. **并行测试执行**：支持多个测试用例并行运行
4. **自定义断言**：支持用户定义的断言函数
5. **集成CI/CD**：支持持续集成流水线

## 错误处理

1. **网络超时**：自动重试机制
2. **元素未找到**：智能等待和重试
3. **断言失败**：详细错误信息和建议
4. **系统异常**：完整的错误堆栈和日志
5. **工件归档失败**：截图移动失败会输出错误日志并保留原始位置

## 性能考虑

1. **测试执行效率**：并行执行和缓存机制
2. **资源占用**：及时清理临时文件，并在截图搬迁后清理`.playwright-mcp`目录中的历史文件
3. **报告生成速度**：异步处理和模板优化

## 安全考虑

1. **敏感信息保护**：测试数据加密存储
2. **访问权限控制**：测试环境隔离
3. **日志脱敏**：自动识别和脱敏敏感信息

## 后续规划

1. **断言解析增强**：让Claude输出更结构化的断言诊断
2. **执行策略调优**：为常见操作提供可复用的Prompt片段
3. **报告模版化**：支持自定义Markdown模版或导出HTML
