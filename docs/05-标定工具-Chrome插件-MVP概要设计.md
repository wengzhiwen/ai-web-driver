# 05-标定工具 — Chrome 插件 MVP 概要设计

**版本**：v0.1.9（2025-10-18）
**状态**：已实现 / 生产就绪（MVP 功能完整）  
**适用范围**：仅限“打标（标注）”环节；**回放、批量执行、截图比对**继续由既有执行架构承担。

---

## 0. 背景与目标
- 现状：Web GUI 方案在浏览器前端直连自动化后端时遇到 CORS / 同源 / iframe 限制与复杂度爆炸。
- 取舍：将“打标”能力前移到 **Chrome 扩展**，在用户已打开的真实页面内直接采集元素信息与候选选择器，并在侧栏进行管理与导出。
- 目标：
  - **稳定、低侵入** 的打标体验（不依赖后端服务，不暴露 wsEndpoint）。
  - **直观可视化**（Hover 高亮、点击即记、侧栏 DOM 树可浏览）。
  - **标准化输出** site profile JSON，**与既有执行器无缝对接**。

> 非目标（MVP）：执行/回放、截图、并发、CI、远程校验、模型辅助生成选择器（可在后续版本接入）。

---

## 1. MVP 范围（Must / Should / Could）
### Must（MVP 必须）✅ **已实现**
1. **页面内打标** ✅：
   - Alt+P 切换"标注模式"。
   - 标注模式下，鼠标移动时 **高亮命中元素**；点击后记录一条"标注项"。
2. **侧边面板（Side Panel）** ✅：
   - 显示当前激活标签页的 **DOM 树（智能快照）**；点击节点→页面高亮；**双击节点→加入标注**。
   - 显示 **当前页面标注列表**：查看、备注/描述编辑、删除、统计（计数）。
3. **数据采集字段**（每个标注项） ✅：
   - `url`（自动标准化去除query/hash）
   - `fingerprint`（`tag`、`id`、`data-testid`、`aria-label`、`title`、`value`、`placeholder`、简短 `text`）
   - 候选选择器 `candidates[]`（基于唯一性和稳定性的智能算法生成）
   - `cssPath`（从 `<html>` 起的结构化路径）
   - `rect`：`{x,y,width,height,scrollX,scrollY,dpr}`（用于可视化与离线对齐）
4. **本地持久化** ✅：`chrome.storage.local`，按 **页面 URL（标准化）** 分组存储。
5. **导出 Site Profile JSON 到本地** ✅：
   - 点击"导出"，使用 `chrome.downloads` 生成符合site_profiles标准的JSON文件。
   - **标准化输出格式**：完全符合项目site_profiles schema。

### Should（优先增强） ✅ **已实现**
- 侧栏 **Frame 列表**（基于 `webNavigation.getAllFrames`）与顶层/子 frame 的 DOM 快照切换。
- **智能节点过滤**：自动排除script、style、link、meta、noscript等无关节点。
- **增强搜索功能**：支持搜索文本内容、value属性、placeholder、title等。
- **DOM树加载能力提升**：深度15层，节点数2000个，折叠深度6层。
- **界面简化**：移除冗余的时间戳和编号显示，专注核心内容。

### Could（后续版本）
- 与后端（Playwright）建 WS，做 **唯一性/可点击性校验打分** 回显。
- 录制“复合动作”草案（点击、输入、选择）并导出步骤草图。
- 标注冲突检测与合并（多人协作）。

---

## 2. 典型用例 / 用户故事
1. **标注员** 在一个商品详情页打标：打开侧栏 → Alt+P → 依次点击“标题、价格、加入购物车按钮” → 在侧栏补充描述 → 导出 JSON → 提交至执行器验证。
2. **质检/开发** 接收 JSON，在既有执行器中进行回放验证，输出“最佳选择器”并回写（未来版本可自动回传并在侧栏显示打分）。

**验收标准（Given/When/Then）**
- Given 已安装插件、打开目标网页；When 开启标注模式并点击元素；Then 侧栏出现该元素的标注项，包含 Must 级字段且 Overlay 高亮准确。
- Given 已有 ≥1 页标注；When 点击“导出”；Then 浏览器保存一个 JSON 文件，结构符合数据契约映射，并能被现有执行器成功解析。

---

## 3. 交互与信息架构
### 3.1 页面内 Overlay
- 结构：全屏固定层，`pointer-events: none`；仅含一个边框盒。
- 行为：
  - 标注模式开启 → `mousemove` 节流（`requestAnimationFrame`）→ 对 `elementFromPoint` 高亮。
  - `click` 捕获阶段阻止默认与冒泡（仅在标注模式）。

### 3.2 侧边面板（Side Panel）
- 头部：当前页 URL（省略显示）+ Frame 选择下拉（框架 ID + URL）。
- 左栏：DOM 树（默认深度=3、每层 ≤60 子节点；可刷新/过滤）。
  - 单击节点：对该 `cssPath` 执行高亮消息。
  - 双击节点：加入标注（生成候选选择器并存储）。
- 右栏：标注列表
  - 展示：时间、简要指纹、候选选择器。
  - 操作：编辑描述、删除项、导出 JSON、清空站点。

### 3.3 快捷键
- Alt+P：开启/关闭标注模式（全局，仅在可注入页面生效）。

---

## 4. 数据契约（Site Profile JSON）
> 说明：插件已实现与项目site_profiles标准的完全对接，输出格式与 `site_profiles/www.runjplib.com.json` 保持一致。

### 4.1 实际输出结构（v0.1.9已实现）
```json
{
  "version": "20251018T143000Z",
  "pages": [
    {
      "id": "products",
      "name": "example.com-products",
      "url_pattern": "/products/123",
      "version": "20251018T143000Z",
      "generated_at": "20251018T143000Z",
      "generated_by": "chrome_extension_manual",
      "aliases": {
        "element_1": {
          "selector": "[data-testid=\"add-to-cart\"]",
          "description": "加入购物车按钮",
          "role": "按钮",
          "confidence": 0.8
        },
        "element_2": {
          "selector": "input[type=\"text\"]#search",
          "description": "搜索输入框",
          "role": "文本输入框",
          "confidence": 0.8
        }
      }
    }
  ]
}
```

### 4.2 字段说明
- `version`：导出版本号（格式：YYYYMMDDTHHMMSSZ）
- `pages[]`：页面列表，按URL路径聚合
  - `id`：页面唯一标识（基于URL路径生成）
  - `name`：页面名称（基于域名和路径生成）
  - `url_pattern`：页面URL模式
  - `version`：页面版本号
  - `generated_at`：生成时间
  - `generated_by`：生成方式（"chrome_extension_manual"）
  - `aliases`：元素别名映射
    - `element_N`：元素别名（N从1开始编号）
      - `selector`：推荐CSS选择器
      - `description`：用户描述（可编辑）
      - `role`：元素角色（按钮、链接、输入框等，由系统自动推断）
      - `confidence`：置信度（默认0.8）

### 4.3 智能角色推断算法
插件会根据HTML标签自动推断元素角色：
- `button` → "按钮"
- `input[type="text"]` → "文本输入框"
- `input[type="submit"]` → "提交按钮"
- `a` → "链接"
- `select` → "下拉选择框"
- `img` → "图片"
- `nav` → "导航栏"
- `header` → "页头"
- `footer` → "页脚"
- 其他标签 → "元素"

---

## 5. 技术架构（MV3）
### 5.1 组件与职责
- **Content Script（cs.js）**：
  - 负责 Overlay 高亮、标注模式事件、DOM 树快照（受限深度/广度）、构造标注项。
  - 与 Side Panel/Background 通过 `chrome.runtime.sendMessage` 通讯。
- **Background Service Worker（bg.js）**：
  - 负责本地存储汇总（`chrome.storage.local`）与简单路由；
  - 提供清理、删除、聚合导出等操作。
- **Side Panel（sidepanel.html/js）**：
  - UI：DOM 树与标注列表；
  - 交互：刷新快照、过滤、节点高亮、双击加入、导出 JSON、清空站点。
- **权限**：
  - `permissions`: `scripting`, `tabs`, `activeTab`, `storage`, `downloads`, `webNavigation`
  - `host_permissions`: `<all_urls>`（上线可收敛为白名单）。

### 5.2 DOM 树快照策略 ✅ **已实现优化**
- **智能快照**：采用分批渲染和懒加载机制，支持大型页面
- **加载能力**：深度15层，节点数2000个，默认maxChildren=500
- **智能节点过滤**：自动排除script、style、link、meta、noscript等无关节点
- **节点字段**：`tag`/`id`/`class`/`data-testid`/`value`/`placeholder`/`text`/`cssPath`/`children[]`
- **懒加载机制**：前6层节点直接加载，超过6层按需展开
- **性能优化**：折叠深度6层，预加载深度5层，分批渲染避免阻塞

### 5.3 Frame & Shadow DOM（MVP 策略）
- MVP：
  - 支持顶层 frame DOM 树；
  - **跨域 iframe**：先通过“Frame 列表”切换到目标 frame（增加可见性，不强行穿越）。
- 增强：
  - 对 `content_scripts` 使用 `all_frames:true`；为相同源 iframe 注入并快照；
  - 记录 `frameId` 与 `frameChain`（后续回放可用）。
- Shadow DOM：
  - 命中元素路径使用 `composedPath()` 获取实际叶子；
  - `cssPath` 可用自定义 `>>>` 语法表示穿透（后续版本）。

### 5.4 搜索功能 ✅ **已实现增强**
- **多维度搜索**：支持文本内容、value属性、placeholder、title、name等
- **智能优先级**：优先搜索文本内容，其次搜索常用属性
- **搜索属性**：支持所有HTML属性和属性名搜索
- **实时过滤**：输入时即时过滤DOM树节点
- **性能优化**：高效的匹配算法，支持大型页面快速过滤

### 5.5 性能与稳定性 ✅ **已实现优化**
- 事件节流：`mousemove` 使用 rAF；
- Overlay 复用单节点，避免频繁创建/销毁；
- 大页支持：DOM 快照深度15层，节点数2000个，按需加载；
- Background 消息路由优化，统一消息处理机制；
- Service Worker兼容性：使用Data URL替代Blob URL；
- 初始化优化：DOM元素验证和事件绑定时机控制。

### 5.6 安全与隐私
- 不外发任何页面数据至网络；
- 仅本地存储，导出由用户显式触发；
- 避免采集敏感字段（不抓取完整 innerHTML，不做截图）。

---

## 6. 兼容性与限制
- 运行环境：Chrome ≥ 114（支持 Side Panel API），Edge ≥ 114（API 差异需验证）。
- 不能注入的页面：`chrome://*`、Chrome Web Store、系统 PDF Viewer 等。
- 一些站点的 CSP 不影响扩展的 **content script** 执行（隔离世界）；避免向页面注入 inline 脚本。

---

## 7. 质量保障（MVP 测试清单）
- [x] **安装/升级**：侧栏可打开，首屏加载正常（v0.1.9已验证）；
- [x] **快捷键**：Alt+P 能开/关标注模式；
- [x] **高亮准确**：不同缩放（DPR=1/2/2.5）与滚动位置下，覆盖框与元素对齐；
- [x] **DOM树功能**：点击高亮、双击加入；智能搜索生效；支持深度15层；
- [x] **标注项字段**：完整（url/fingerprint/candidates/cssPath/rect/智能角色）；
- [x] **持久化**：页面刷新后标注仍在，按页面URL分组存储；
- [x] **导出文件**：JSON结构符合site_profiles标准，与执行器无缝对接；
- [x] **受限页面处理**：提示"需要初始化插件"，提供手动注入机制；
- [x] **大页面支持**：深度15层，节点数2000个，分批渲染，交互响应流畅；
- [x] **搜索功能**：支持文本、value、placeholder等多维度搜索；
- [x] **界面简化**：标注列表无冗余时间戳和编号，专注核心内容。

---

## 8. 里程碑与交付 ✅ **已完成**

### M0（已交付 - v0.1.9）
1. ✅ **骨架搭建**：manifest v0.1.9、Side Panel、Content Script、Storage、Downloads
2. ✅ **Overlay 与标注模式**：高亮/点击记录/快捷键/手动注入机制
3. ✅ **DOM 树快照与交互**：智能快照/懒加载/分批渲染/智能搜索
4. ✅ **数据契约与导出**：完全符合site_profiles标准格式
5. ✅ **兼容性与优化**：DPR/滚动/大页/受限页面/Service Worker兼容性
6. ✅ **用例联调**：与项目执行器无缝对接验证

### 已实现增强功能（超出原始MVP范围）
- 🚀 **DOM加载能力提升**：深度15层，节点数2000个
- 🔍 **智能搜索功能**：多维度搜索（文本、value、属性等）
- 🎯 **智能节点过滤**：自动排除无关节点
- ✨ **界面简化**：移除冗余信息，专注核心内容
- 🧠 **智能角色推断**：自动识别元素角色（按钮、链接、输入框等）
- 🛡️ **错误处理增强**：完善的初始化和通信机制

**实际产出**：
- ✅ **生产就绪的MV3插件包**（calibration-chrome-extension/）
- ✅ **完整的技术文档**（README.md v0.1.9）
- ✅ **标准化的site_profiles输出**，与项目执行器完全兼容
- ✅ **稳定的功能验证**：经过多轮迭代和用户测试验证

---

## 9. 风险与对策 ✅ **已解决**

| 风险 | 影响 | 解决状态 | 对策（已实施） |
|---|---|---|---|
| 大型页面 DOM 树渲染卡顿 | 侧栏滚动/展开不流畅 | ✅ **已解决** | 分批渲染 + 懒加载机制 + 智能节点过滤 + 深度15层/节点2000个 |
| 跨域 iframe 需求强 | 无法在侧栏统一浏览所有子树 | ✅ **已解决** | Frame 列表切换 + webNavigation API 支持 |
| 选择器脆弱 | 回放失败率上升 | ✅ **已解决** | 智能选择器算法 + 多策略候选 + 唯一性评分 |
| 用户误操作（误点/误删） | 标注质量下降 | ✅ **已解决** | 确认弹窗 + 导出预检查 + 操作反馈 |
| Service Worker兼容性 | MV3环境下功能异常 | ✅ **已解决** | Data URL替代Blob URL + 消息路由优化 |
| 初始化时机问题 | DOM元素绑定失败 | ✅ **已解决** | 元素验证机制 + 手动注入机制 |
| 权限过宽引发审查风险 | 上架/企业分发受阻 | ⚠️ **待优化** | 上线前将 `<all_urls>` 收敛为白名单域 |

### 新增技术债务
| 风险 | 影响 | 计划对策 |
|---|---|---|
| 复杂页面性能 | DOM节点过多时的交互响应 | 已通过分批渲染和懒加载解决 |
| 选择器算法优化 | 更智能的唯一性识别 | 后续版本可接入AI辅助生成 |
| 用户体验优化 | 学习成本和操作效率 | 持续收集用户反馈进行迭代 |

---

## 10. 开放问题（已解决/后续优化）

### 已解决的问题 ✅
1. **Site Profile schema对齐** - ✅ 已完全实现与项目site_profiles标准对接
2. **跨域iframe支持** - ✅ 已实现Frame列表切换功能
3. **导出格式标准化** - ✅ 输出格式完全符合`site_profiles/www.runjplib.com.json`

### 后续优化方向
1. **AI辅助选择器生成** - 接入LLM提供更智能的选择器建议
2. **批量操作功能** - 支持批量标注和导出多个页面
3. **截图对齐功能** - 提供可视化校验和截图对比
4. **协作功能** - 多用户标注协作和冲突解决
5. **性能进一步优化** - 针对超大型应用的性能优化

---

## 11. 附录：选择器优先级（v0.1.9已实现）

### 实际实现的选择器生成算法
插件采用基于**唯一性和稳定性**的智能算法生成候选选择器：

1. **第一优先级**：`#id`（唯一标识符）
2. **第二优先级**：`[data-testid]`、`[data-qa]`（测试专用属性）
3. **第三优先级**：`[role]`、`[aria-label]`、`[title]`（可访问性属性）
4. **第四优先级**：`[name]`、`[type]`（表单属性）
5. **第五优先级**：`.class`（样式类名，避免过长的class链）
6. **第六优先级**：`tag:nth-of-type(n)`（结构化位置）
7. **兜底选择器**：完整`cssPath`（绝对路径）

### 智能评分机制
- **唯一性评分**：在页面中的唯一性程度
- **稳定性评分**：选择器在不同页面加载时的稳定性
- **简洁性评分**：选择器长度和复杂度
- **可读性评分**：人工理解和维护的难易程度

### 输出格式
每个标注项生成最多5个候选选择器，按综合评分排序，`bestSelector`取候选列表首位。

> 注：算法已在实际项目中验证，能够有效处理现代Web应用的复杂DOM结构。

