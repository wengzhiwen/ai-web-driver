# 编译器 MVP 概要设计

## 1. 背景与目标
编译器负责将 QA 的自然语言 TestRequest 转换为执行器可理解的 ActionPlan DSL。MVP 目标是实现"单用例、单流程"编译链路，验证从文本到结构化指令的可行性，并输出包含定位信息的强类型 DSL，供执行器直接消费。

**已完成升级**：
- ✅ 数据驱动编译：通过占位符替换机制扩展为多个测试用例
- ✅ LLM质量优化：基于role字段的通用智能修正框架
  - 基于role属性的强化框架
  - 优化DSL提示词，强调role字段的使用规则
  - 完全通用化，适用于任何网站
- ✅ 图片验证优化：基于HTML标准的通用规则
  - 自动移除img选择器中的`:has-text()`
  - 强制图片验证使用kind=visible

## 2. 范围与非目标
- 范围：
  - 接收单个 TestRequest（Markdown格式文本步骤 + 可选元信息）。
  - 读取指定 SiteProfile（已标注元素、页面跳转关系）。
  - 通过LLM解析自然语言步骤，映射到 `goto`、`click`、`fill`、`assert` 等基础动作。
  - 产出带 Playwright selector 的 ActionPlan JSON，覆盖顺序流程与简单断言。
  - **新增**：支持从数据集合（JSON 格式）驱动的测试用例生成。
  - **新增**：自动进行占位符替换和转译（性别、价格倍数等）。
- 非目标：
  - 不支持多用例批量编译、循环/分支逻辑、复杂数据驱动。
  - 不处理跨页上下文推理、复杂条件判断、结果回写。
  - LLM 生成的结果基于已有 SiteProfile，不自动发现新元素。

## 3. 输入与输出
- **输入**：
  - `TestRequest`：Markdown格式文件，包含测试标题、背景、步骤列表（每步可包含参数、期望值）。
  - `SiteProfile`：JSON格式文件，包含页面列表、别名→定位器映射、页面描述等。
  - `ActionPlan Schema`：JSON Schema文件，定义输出格式规范。
  - **新增**：`DataSet`：JSON 格式文件，包含多条结构化数据项目，每项可用于驱动一个测试用例。
- **输出**：
  - **单 ActionPlan（编译阶段）**：
  ```json
  {
    "meta": {
      "testId": "RUNJPLIB-SEARCH-TSUKUBA",
      "baseUrl": "https://www.runjplib.com"
    },
    "steps": [
      {"t": "goto", "url": "/"},
      {"t": "fill", "selector": "#universitySearch", "value": "s_chinese_name"},
      {"t": "click", "selector": "#searchButton"},
      {"t": "assert", "selector": "ul#university-list", "kind": "visible"}
    ]
  }
  ```
  - **多 ActionPlan（替换阶段）**：
  ```json
  {
    "meta": {
      "testId": "RUNJPLIB-SEARCH-TSUKUBA-001",
      "dataSource": "dataset.json#0"
    },
    "steps": [
      {"t": "goto", "url": "/"},
      {"t": "fill", "selector": "#universitySearch", "value": "软萌心语 男发"},
      {"t": "click", "selector": "#searchButton"},
      {"t": "assert", "selector": "ul#university-list", "kind": "visible"}
    ]
  }
  ```

## 4. 核心流程

### 阶段一：编译阶段（保留占位符）
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
   - **通用智能修正**：
     - 基于role的click修正：检测role="文本"的错误点击，自动查找相关的role="按钮"或"链接"元素
     - 图片验证修正：自动移除img选择器中的`:has-text()`，强制kind=visible（HTML标准）
     - 语义关联匹配：通过名称、描述和页面上下文查找最佳替代元素
6. **验证与输出**：
   - Schema 合规性验证
   - Playwright 语法校验
   - 生成 testId 和完善 meta 信息
   - **输出模板 ActionPlan**（保留占位符）到 `action_plans/<timestamp>/cases/<case_name>/action_plan.json`

### 阶段二：数据驱动替换阶段（占位符→实际数据）

1. **数据集加载**：
   - 加载 JSON 格式的数据集文件
   - 提取目标类别的数据项列表
   - 对每个数据项执行以下操作

2. **占位符提取**：
   - 从模板 ActionPlan 中扫描所有 s_ 前缀的占位符
   - 分类占位符类型：
     - 普通占位符：s_field_name
     - 转译占位符：s_gender（需性别转译）
     - 表达式占位符：s_price*2（需乘法计算）

3. **占位符转译**：
   - `s_gender` 转译规则：
     - `m` → `男`
     - `f` → `女`
     - `m,f` → `通用`
   - 表达式占位符处理：
     - 正则匹配 `s_<field>*<multiplier>` 模式
     - 从数据项中提取 `<field>` 值
     - 执行 `值 × multiplier` 计算
     - 返回计算结果

4. **文本替换与验证**：
   - 对 ActionPlan 中的每个字段执行文本替换
   - 替换目标字段：`value`、`url`、内嵌的文本断言值等
   - 记录每个替换的统计信息
   - 验证是否存在无法替换的占位符（错误）

5. **错误收集与输出**：
   - **替换错误**：
     - 数据缺失错误：占位符在数据项中不存在
     - 表达式错误：倍数计算异常（非数字）
     - 转译错误：非法的转译值
   - **统计输出**：
     - 成功替换数量
     - 失败替换数量
     - 各类型错误的数量统计
   - **详细输出**：
     - 按数据项逐一输出
     - 记录每个数据项的替换状态
     - 详列所有异常和错误信息

6. **测试用例输出**：
   - 为每个数据项生成带序号的 ActionPlan
   - 格式：`<base_name>_<index>_<timestamp>.json`
   - 更新 meta 信息：
     - testId 增加序号：`<testId>_<index>`
     - 新增 dataSource 字段：`dataset.json#<index>`

## 5. 模块划分
- **TestRequestParser**：解析 Markdown 格式的测试需求文件。
- **SiteProfileLoader**：加载和解析站点配置 JSON 文件。
- **LLMClient**：封装 LLM API 调用，支持重试和超时机制。
- **LLMAgents**：提供提示词生成、DSL 规范说明等辅助功能。
- **LLMCompilationPipeline**：协调整个编译流程的核心引擎。
- **新增 PlaceholderProcessor**：占位符检测、提取、转译、替换的集中处理模块。
- **新增 DataDrivenCompiler**：数据驱动编译逻辑，协调数据加载、占位符替换、错误收集、结果输出。
- **CLI 入口**：提供命令行接口，支持参数配置和结果输出。

## 6. 占位符处理详细规范

### 6.1 占位符识别
- 格式：`s_<field_name>` 或 `s_<field_name>*<multiplier>`
- 正则模式：`s_[a-zA-Z_][a-zA-Z0-9_]*(?:\*\d+)?`
- 出现位置：步骤的 `value` 字段、断言的文本值、URL 路径等

**占位符示例**：
```
- 在搜索框中键入"s_chinese_name"
- 验证价格为"s_price"M币
- 点击"30天"按钮，验证价格变为"s_price*2"M币
- 验证适用性别为"s_gender"
```

### 6.2 转译规则

#### 普通占位符
直接从数据项中取值替换。

```
占位符：s_chinese_name
数据项: { "s_chinese_name": "软萌心语 男发" }
替换结果："软萌心语 男发"
```

#### 性别转译占位符
自动进行性别值转译。

```
占位符：s_gender
数据项: { "s_gender": "m" }
转译规则：m → 男, f → 女, m,f → 通用
替换结果："男"
```

#### 表达式占位符
支持乘法计算。

```
占位符：s_price*2
数据项: { "s_price": "550" }
计算过程：550 × 2 = 1100
替换结果："1100"
```

**转译规则总表**：

| 占位符类型 | 转译规则 | 示例 |
|-----------|--------|------|
| s_gender | m→男, f→女, m,f→通用 | "s_gender" + "m" → "男" |
| s_price*N | 取值×N | "s_price*3" + 550 → "1650" |
| 其他占位符 | 直接替换 | "s_chinese_name" + "软萌心语 男发" → "软萌心语 男发" |

### 6.3 错误处理

| 错误类型 | 触发条件 | 处理方式 |
|---------|--------|--------|
| missing_field | 占位符对应的数据字段不存在 | 记录错误，跳过该项 |
| expression_error | 表达式计算失败（非数字值） | 记录错误，跳过该项 |
| translation_error | 性别值转译失败（非 m/f/m,f） | 记录错误，跳过该项 |
| unreplaced_placeholder | 替换后仍存在占位符 | 记录警告 |

### 6.4 数据驱动编译流程图

```
┌─────────────────────────┐
│  TestRequest + Profile  │
│  (with placeholders)    │
└────────────┬────────────┘
             │
             ▼
    ┌────────────────┐
    │ LLM Compilation│
    │   (Phase 1)    │
    └────────┬───────┘
             │
             ▼
┌─────────────────────────────┐
│  Action Plan Template       │
│  (with placeholders)        │
└──────┬──────────────┬───────┘
       │              │
       │    ┌─────────┘
       │    │
       ▼    ▼
┌────────────────────┐    ┌──────────────┐
│  DataSet JSON      │    │ PlaceholderProcessor
│  (multiple items)  │    │ (translate & replace)
└────────┬───────────┘    └──────┬───────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │  Data-Driven Compilation│
        │   (Phase 2)             │
        └─────────────┬───────────┘
                      │
           ┌──────────┼──────────┐
           ▼          ▼          ▼
        Case1      Case2      Case3
       (filled)   (filled)   (filled)
```

## 7. 校验与错误处理
- Schema 校验：使用 JSON Schema 验证 LLM 生成的 ActionPlan 结构正确性。
- 多轮重试机制：LLM 输出不符合规范时自动重试，最多尝试指定次数。
- Playwright 语法校验：确保 selector 语法兼容，禁用不支持的伪类和 XPath。
- 完整性检查：验证必要参数（如 fill 操作的 value 值）是否缺失。
- **新增占位符校验**：
  - 验证模板 ActionPlan 中的所有占位符是否在数据集中有对应字段
  - 验证数据项的类型匹配（特别是表达式占位符需要数字类型）
- **输出校验**：最终 ActionPlan 通过完整验证流程，确保执行器能直接运行。

## 8. 运行形态

### 8.1 单用例编译（现有功能）
```bash
python -m compiler_mvp.llm_cli \
  --request test_requests/测试需求1.md \
  --profile site_profiles/www.runjplib.com.json
```

### 8.2 数据驱动编译（新增功能）
```bash
python -m compiler_mvp.llm_cli \
  --request test_requests/AU01商城测试需求_sample.md \
  --profile site_profiles/au_shop.json \
  --dataset results/excel_datasets/20251102/10월 번역 파일_20251102T132423.json \
  --dataset-category production_avatar
```

### 8.3 支持参数
- `--attempts`：最大重试次数（默认3次）
- `--temperature`：LLM 温度参数（默认0.2）
- `--api-timeout`：API 调用超时时间
- `--plan-name`、`--case-name`：自定义输出目录名称
- **新增**：`--dataset`：数据集 JSON 文件路径
- **新增**：`--dataset-category`：数据集中的目标类别（如 production_avatar）
- **新增**：`--skip-llm`：跳过 LLM 编译，直接使用已有的模板进行数据驱动替换
- **新增**：`--output-stats`：输出替换统计信息和详细错误日志

### 8.4 输出结构
- **仅编译**：`action_plans/<timestamp>_llm_plan/cases/<case_name>/action_plan.json`
- **编译+替换**：
  ```
  action_plans/<timestamp>_data_driven_plan/
  ├── action_plan_template.json          # 模板（保留占位符）
  ├── stats.json                         # 替换统计
  ├── errors.json                        # 错误详表（如有错误）
  └── cases/
      ├── <case_name>_001.json
      ├── <case_name>_002.json
      └── ...
  ```

#### stats.json 示例

```json
{
  "total_items": 100,
  "successful_items": 98,
  "failed_items": 2,
  "error_summary": {
    "missing_field": 1,
    "expression_error": 1
  },
  "timestamp": "2025-11-02T13:30:00Z"
}
```

#### errors.json 示例

```json
{
  "total_errors": 2,
  "by_type": {
    "missing_field": [
      {
        "placeholder": "s_parts",
        "field_name": "parts",
        "data_index": 5,
        "message": "数据项中缺失字段: parts"
      }
    ],
    "expression_error": [
      {
        "placeholder": "s_price*2",
        "field_name": "price",
        "data_index": 23,
        "message": "无法计算表达式: abc * 2"
      }
    ]
  },
  "summary": {
    "missing_field": 1,
    "expression_error": 1
  }
}
```

### 8.5 使用示例

#### 示例 1：电商商品功能测试

**场景**：测试商城商品搜索、详情显示和购买选项功能

**TestRequest**（AU01商城测试需求_sample.md）：
```markdown
## 测试步骤
1. 在顶部的搜索框中键入"s_chinese_name"
2. 点击搜索按钮
3. 验证搜索结果显示"s_chinese_name"
4. 验证性别标签为"s_gender"
5. 验证基础价格为"s_price"M币
6. 点击"30天"按钮，验证价格变为"s_price*2"M币
7. 点击"永久"按钮，验证价格变为"s_price*6"M币
```

**执行命令**：
```bash
python -m compiler_mvp.llm_cli \
  --request test_requests/AU01商城测试需求_sample.md \
  --profile site_profiles/au_shop.json \
  --dataset results/excel_datasets/20251102/10월\ 번역\ 파일_20251102T132423.json \
  --dataset-category production_avatar \
  --case-name shop_product \
  --output-stats
```

**输出**：
- 生成 300+ 个测试用例（每个数据项一个）
- 每个用例包含完整的商品搜索、显示验证和价格计算
- stats.json 记录成功/失败统计
- errors.json 列出所有异常数据项

#### 示例 2：快速迭代（跳过 LLM）

如果已经有模板 ActionPlan，可以跳过 LLM 编译，直接进行数据驱动替换：

```bash
python -m compiler_mvp.llm_cli \
  --request test_requests/AU01商城测试需求_sample.md \
  --profile site_profiles/au_shop.json \
  --dataset results/excel_datasets/20251102/10월\ 번역\ 파일_20251102T132423.json \
  --dataset-category production_avatar \
  --skip-llm \
  --plan-name 20251102T132000Z_llm_plan \
  --output-stats
```

### 8.6 错误诊断

启用 `--output-stats` 参数可以在终端输出统计摘要：

```
============================================================
数据驱动编译统计摘要
============================================================
总数据项: 100
成功替换: 98
失败替换: 2

错误统计:
  missing_field: 1
  expression_error: 1
============================================================
```

完整错误详表会保存到 `errors.json`，可用于深入分析和调试。

## 9. 关键特性

### 9.1 核心编译能力
- **LLM 驱动**：核心编译逻辑基于大语言模型，具备自然语言理解能力
- **智能匹配**：通过相似度计算将 LLM 生成的选择器映射到 SiteProfile 中的标准别名
- **文本断言增强**：自动为文本验证添加 `:has-text()` 语法，提升断言准确性
- **上下文传递**：在多步骤操作中智能传递和复用文本参数
- **错误自愈**：通过多轮对话机制修复 LLM 输出的格式和内容错误

### 9.2 数据驱动能力
- **批量扩展**：支持将单个模板 ActionPlan 批量扩展为数据驱动的多个测试用例
- **智能转译**：内置占位符转译规则（性别、价格倍数等），可扩展自定义转译器
- **完整错误报告**：统计与详细输出并行，便于快速定位问题

### 9.3 LLM质量优化与通用化（2025-11-03重构）

#### 核心理念：从标定到编译的质量链
**问题本质**：标定阶段已正确区分了元素role（文本/按钮/链接），但LLM编译时仍选择错误元素

**解决路径**：
1. **强化标定信息利用**：在SiteProfile摘要中显式展示role字段
2. **优化LLM提示词**：明确要求根据role字段选择元素
3. **通用智能修正框架**：基于role属性而非DOM结构进行修正

#### 基于role的智能修正（通用框架）
**方法**：`_correct_click_by_role_mismatch()`

**检测条件**：
- click步骤选择了role为"文本"、"标题"、"标签"的元素

**修正策略**：
1. 在同一页面中查找role为"按钮"或"链接"的候选元素
2. 使用评分系统选择最佳候选：
   - 同一页面: +50分（基础分）
   - 名称关键词匹配: 每个+30分
   - 描述相关性: +40分
   - 语义关联（如商品名称→购买按钮）: +60分
   - 别名置信度: 置信度×20
3. 只有分数≥80时才执行修正（避免误修正）

**特点**：
- ✅ 完全通用：不依赖特定网站的DOM结构
- ✅ 基于标定：充分利用role字段和语义信息
- ✅ 可扩展：易于添加新的语义关联规则

#### 图片验证修正（HTML标准）
**问题**：LLM生成 `img:has-text()` 无效组合（违反HTML标准）

**解决方案**：
- LLM提示词明确说明img元素不包含文本内容
- assert后处理自动检测并移除图片验证中的:has-text()
- 强制图片验证kind=visible，移除value字段
- **通用性**：基于HTML标准，适用于任何网站

#### DSL提示词优化
**核心增强**：
```
6. **根据 role 字段选择正确的元素（关键）**：
   - fill 操作：必须选择 role="输入框" 的元素
   - click 操作：必须选择 role="按钮" 或 role="链接" 的元素
   - assert 操作：可选择 role="文本" 等显示元素

7. **常见错误模式及修正**：
   - ✗ 错误：点击商品名称（role="文本"）
   - ✓ 正确：点击购买按钮（role="按钮"）

9. **标准测试流程示例**：
   - 验证商品存在：assert 商品名称(role="文本")
   - 进入详情页：click 购买/详情按钮(role="按钮")
```

**涉及模块**：
- `compiler_mvp/llm_agents.py`：DSL提示词优化、SiteProfile摘要增强
- `compiler_mvp/llm_pipeline.py`：通用智能修正框架

### 9.4 验证结果

**数据驱动编译测试**：
```
总数据项: 338
成功替换: 338
失败替换: 0
成功率: 100%
```

**端到端测试**：
```
case_002: 16/16步骤通过（灵眸眨眨 女套装）
case_003: 16/16步骤通过（灵眸眨眨 女发）
case_013: 16/16步骤通过（俏皮眨眼 女裤）
case_253: 16/16步骤通过（华裳烁彩 女发）
```

**关键选择器验证**：
```json
{
  "购买按钮": "div.proView_list div.list_buyBox > a.buy_list",  // ✓ 正确
  "图片验证": "div.proView_list div.item_img > img",            // ✓ 无:has-text()
  "30天按钮": "div#days > a:nth-child(2)",                      // ✓ 未被误修正
  "永久按钮": "div#days > a:nth-child(3)"                       // ✓ 未被误修正
}
```
