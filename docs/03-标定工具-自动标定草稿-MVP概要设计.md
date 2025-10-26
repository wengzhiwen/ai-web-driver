# 标定工具 CLI 自动标定草稿设计

## 1. 背景与目标
- 目的：在没有 GUI 的前提下，通过命令行入口完成页面抓取与初步 DOM 标定，快速验证 LLM 自动标定草稿的可行性。
- 范围：输入单个 URL，利用 Playwright 抓取页面结构，调用 LLM 生成 Site Profile 片段，并支持合并到既有 Profile 文件。
- 定位：为后续可视化标定工具提供基础能力验证，聚焦自动化程度、输出格式与可扩展性。

## 2. 非目标
- 不提供交互式 DOM 选择或人工修改流程。
- 单次执行仅针对一个 URL 的快照，若需多页面需通过多次命令合并。
- 不解决页面登录/鉴权等复杂前置条件，仅支持匿名可访问的页面。
- 不引入复杂的差异合并策略，冲突处理先以追加版本号或简单覆盖为主。

## 3. 前置假设
- Playwright 与浏览器依赖已安装，可通过 `venv/` 环境执行。
- LLM 访问密钥已在env文件中定义好，直接通过dotenv取出，访问LLM请使用openai python sdk（在compiler mvp中已经有应用）。
- Site Profile 的基本 schema 已在项目内约定，字段需与编译器消费的一致（页面、元素、别名、selector、版本元信息等）。
- CLI 日志输出遵循 `./log` 目录、按自然日滚动的约定。

## 4. 核心流程
1. **输入解析**：读取 CLI 参数，包含目标 URL、可选的输出路径、合并目标 Profile、LLM 模型配置等；若用户通过 `--page-name` 指定页面名称，则后续流程固定该名称，不再触发自动命名；`--test-case` 可多次提供文件或文本，作为 LLM 的功能理解参考。
2. **页面抓取**：
   - 使用 Playwright headless 模式加载目标 URL。
   - 支持设置超时与可选的等待策略（如 `--wait-for` selector）。
   - 抽取 DOM 树、可访问性节点、关键属性（tag、role、name、text、data-test、aria-*）。
   - 生成结构化快照（压缩后的 JSON），存入临时文件供 LLM 消费。
3. **LLM 标定**：
   - 构造提示词，包含页面上下文（URL、标题）、抽取的 DOM 片段、预设的标定指导语。
   - 先整体理解整个页面的大致功能，再逐功能区块进行解析和抽取。
   - 适当控制上下文长度：对 DOM 按区域/深度分块（事实上现代LLM的上下文长度很夸张不用过分小心），依次请求 LLM，最后聚合结果。
   - 若提供测试用例，上述提示词会额外描述这些用例的业务目标与关键交互，引导 LLM 按照测试关注点挑选元素。
   - 输出包含页面元信息、元素别名、定位器建议、优先级标签、自然语言描述等。
4. **结果组装**：
   - 将 LLM 返回的标定结果转化为标准 Site Profile 页面节点。
   - 自动生成唯一版本号（`页面ID + timestamp`）。
   - 记录生成过程中的警告/置信度信息。
5. **文件落地**：
   - 如果指定 `--append-to`，加载现有 Profile，按页面 ID 合并：
     - 若页面不存在，直接追加。
     - 若页面存在，根据版本策略（默认追加新版本并保留旧数据）。
   - 支持通过多次运行 CLI、重复指定同一 `--append-to`，逐步为一个站点累积多页面的标定结果。
   - 否则写入新的 Profile 草稿文件（默认 `site_profiles/drafts/<slug>.json`）。
6. **输出反馈**：在 CLI 输出概要信息（成功页面数、元素计数、警告），并提示相关文件路径。

## 5. 组件划分
- **CLI 层 (`cli.py`)**：解析参数、驱动后续流程；负责人机交互提示。
- **PageFetcher**：封装 Playwright 操作，提供 `fetch_dom(url, wait_for=None)`，返回页面 HTML、A11y 树、截图（可选）。
- **DomCompressor**：对原始 DOM 进行裁剪/分块，控制 token 数；支持结构化输出（节点深度、标识属性、纯文本摘要）。
- **LLMAnnotator**：
  - 构建提示词模版；
  - 管理分块请求与重试；
  - 负责将 LLM 的 JSON 输出反序列化，捕获并修复常见格式问题。
- **ProfileAssembler**：将标定片段转为 Site Profile 页面对象，生成版本号、补充元信息。
- **ProfileMerger**：负责与既有 Profile 合并，解决页面冲突；记录冲突日志。
- **OutputWriter**：统一写入 JSON、日志、调试快照。

## 6. CLI 参数草案
```
python -m profile_builder.cli \
  --url https://example.com/products \
  --page-name '产品列表页' \
  --test-case docs/test_cases/products_smoke.md \
  --output site_profiles/drafts/products_autogen.json \
  --append-to site_profiles/shop.json \
  --max-depth 5 \
  --wait-for 'data-test=product-list'
```
- 上述命令可重复执行，针对不同 URL 指定同一个 `--append-to` 文件，以逐页补齐同一站点的 Site Profile。
- `--url`（必填）：目标页面 URL。
- `--output`：独立输出文件路径；未指定时默认写入 `site_profiles/<时间戳>/<域名-路径>.json`，文件名会按需截断并附加哈希避免过长。
- `--append-to`：合并目标 Profile 文件路径。
- `--page-name`：显式指定页面名称，LLM 输出与后处理均以该名称为准，避免详情页场景下的额外命名推测。
- `--test-case`：可多次传入，支持文件路径或直接文本；CLI 会读取内容并附加到 LLM 提示词中，用于强调需要重点覆盖的业务流程。
- `--temperature`：LLM 采样温度；模型名称沿用环境变量 `MODEL_STD`。
- `--max-depth` / `--max-nodes`：控制 DOM 提取规模（默认 8 / 1000）。CLI 会在标准输出中报告“限制/实际”的深度与节点数量，便于观察抽取情况。
- `--wait-for`：在抓取前等待特定 selector，以提升动态站点稳定性。
- `--include-screenshot`：可选生成页面截图供后续人工校对。
- `--dry-run`：仅生成终端预览，不落地文件。
- `--interactive`：开启交互模式，逐步处理长文本与重复结构。
- 每次运行都会询问页面是否为详情页，用于提示 LLM 在描述时更趋抽象；若为详情页，会依据 URL 自动生成如“博客详情页”等页面名称；当用户已经提供 `--page-name` 时跳过这一自动命名逻辑。
- 针对搜索区域这类容器，CLI 会自动补充输入框与按钮等常用交互元素别名，避免遗漏核心控件。
> 若未指定 `--append-to` 或 `--output`，CLI 会将结果写入 `site_profiles/<时间戳>/<域名-路径>.json`，避免覆盖历史草稿。

## 7. Site Profile 输出结构
```json
{
  "site": {
    "name": "shop",
    "base_url": "https://example.com"
  },
  "pages": [
    {
      "page_id": "products",
      "url_pattern": "/products",
      "version": "2025-10-11T12:00:00+08:00",
      "generated_by": "cli-auto-draft",
      "elements": [
        {
          "alias": "product.list",
          "selector": "data-test=product-list",
          "role": "list",
          "description": "商品列表容器",
          "confidence": 0.78
        },
        {
          "alias": "product.card.title",
          "selector": "data-test=product-card >> h3",
          "role": "heading",
          "description": "商品卡片标题"
        }
      ],
      "navigation": [],
      "notes": "自动标定草稿，需人工复核"
    }
  ]
}
```
- `confidence`：来自 LLM 的置信度或启发式评分。
- `generated_by` + `notes`：帮助人工识别草稿来源。
- 后续人工工具可根据 `version` 做对比与修订。

## 8. 日志与调试
- 日志写入 `./log/profile_builder-YYYYMMDD.log`，记录每次 CLI 运行的关键事件（抓取开始/完成、LLM 调用、输出路径等）。
- 对每个 LLM 请求保存原始 prompt/response（默认存入 `artifacts/<run_id>/llm/`，可通过配置关闭）。
- 若解析失败，输出诊断信息并保留失败片段供手动修复；不在 Site Profile 中存储 warnings，相关提示写入日志。

## 9. 错误处理
- 页面抓取失败：提供明确错误及重试建议（网络、超时、等待 selector 未命中）。
- LLM 响应非法 JSON：尝试自动修复；若仍失败，将响应保存到调试目录并提示人工干预。
- 合并冲突：当页面 ID 冲突且策略为禁止覆盖时终止，并在日志中提示用户先手动处理。
- 文件写入失败：检查路径权限并给出解决建议。

## 10. 交互模式（可选）
- 长文本检测：当节点文本量超过阈值时，先询问是否整体压缩；若用户拒绝，再逐段询问是否删除各段正文直至用户选择保留剩余部分。
- 重复结构检测：当检测到大量结构近似的子节点（评论、推荐列表等）时，询问是否仅保留前 2 条示例，或允许输入自定义保留数量；拒绝则全部保留。
- 所有交互选择会写入日志，便于后续追溯与复现。
