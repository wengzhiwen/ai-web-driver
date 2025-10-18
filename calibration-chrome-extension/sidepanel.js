/**
 * 侧边面板脚本：DOM树展示、标注管理、界面交互
 */

// 全局状态
let currentTabId = null;
let currentFrameId = 0; // 0 = 顶层框架
let currentUrl = "";
let isPickingMode = false;
let allMarks = {};

// DOM元素引用 - 延迟获取，确保DOM加载完成
let elements = {};

function initializeElements() {
  // 获取所有必要的DOM元素
  const elementIds = [
    'currentUrl', 'frameSelector', 'toggleMode', 'filterInput',
    'refreshTree', 'treeContainer', 'marksList', 'exportBtn',
    'clearBtn'
  ];

  const loadedElements = {};
  const missingElements = [];

  // 逐个获取元素并记录缺失的元素
  elementIds.forEach(id => {
    const element = document.getElementById(id);
    if (element) {
      loadedElements[id] = element;
    } else {
      missingElements.push(id);
    }
  });

  // 检查核心元素是否存在
  const coreElements = ['toggleMode', 'exportBtn', 'treeContainer', 'marksList'];
  const missingCoreElements = coreElements.filter(id => !loadedElements[id]);

  if (missingCoreElements.length > 0) {
    console.error('核心DOM元素缺失:', missingCoreElements);
    throw new Error(`核心DOM元素缺失: ${missingCoreElements.join(', ')}`);
  }

  if (missingElements.length > 0) {
    console.warn('部分DOM元素未找到:', missingElements);
  }

  console.log('DOM元素初始化完成，成功获取:', Object.keys(loadedElements).length, '个元素');

  elements = loadedElements;
}

// 工具函数
function $(selector) {
  return document.querySelector(selector);
}

function escapeHtml(text = "") {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function normalizePageUrl(url) {
  try {
    const urlObj = new URL(url);
    urlObj.hash = "";
    urlObj.search = "";
    return urlObj.toString();
  } catch (error) {
    return url;
  }
}

// 获取当前活动标签页
async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tabs[0];
}

// 向content script发送消息 - 简化版本，优先手动注入
async function sendMessageToContent(message) {
  try {
    // 先检查标签页是否还存在
    const tab = await chrome.tabs.get(currentTabId);
    if (!tab) {
      console.error('标签页不存在');
      return null;
    }

    // 直接尝试发送消息
    const response = await chrome.tabs.sendMessage(currentTabId, message, { frameId: currentFrameId });
    return response;
  } catch (error) {
    console.log('Content script通信失败，尝试手动注入:', error.message);

    // 立即尝试注入content script
    const injected = await tryInjectContentScript();
    if (injected) {
      console.log('手动注入成功，重新发送消息...');
      try {
        const response = await chrome.tabs.sendMessage(currentTabId, message, { frameId: currentFrameId });
        return response;
      } catch (retryError) {
        console.error('注入后仍无法通信:', retryError.message);
      }
    }
    return null;
  }
}

// 尝试手动注入content script - 优化版本
async function tryInjectContentScript() {
  try {
    console.log('尝试手动注入content script...');

    // 注入脚本
    await chrome.scripting.executeScript({
      target: { tabId: currentTabId },
      files: ['content-script.js']
    });

    // 注入样式
    await chrome.scripting.insertCSS({
      target: { tabId: currentTabId },
      files: ['overlay.css']
    });

    console.log('Content script手动注入成功');

    // 短暂等待初始化完成
    await new Promise(resolve => setTimeout(resolve, 300));

    // 测试通信是否正常
    try {
      const testResponse = await chrome.tabs.sendMessage(currentTabId, {
        type: "get_page_info"
      });
      if (testResponse?.ok) {
        console.log('Content script通信测试成功');
        return true;
      }
    } catch (error) {
      console.log('Content script通信测试失败，等待更长时间...');
      // 再等待一段时间
      await new Promise(resolve => setTimeout(resolve, 700));

      try {
        const retryResponse = await chrome.tabs.sendMessage(currentTabId, {
          type: "get_page_info"
        });
        if (retryResponse?.ok) {
          console.log('Content script延迟通信测试成功');
          return true;
        }
      } catch (retryError) {
        console.log('Content script延迟通信也失败');
      }
    }

    return true; // 即使通信测试失败，也认为注入成功
  } catch (error) {
    console.error('手动注入content script失败:', error);
    return false;
  }
}

// 初始化框架选择器
async function initializeFrameSelector() {
  try {
    const frames = await chrome.webNavigation.getAllFrames({ tabId: currentTabId });
    elements.frameSelector.innerHTML = '';

    frames.sort((a, b) => a.frameId - b.frameId);

    frames.forEach(frame => {
      const option = document.createElement('option');
      option.value = frame.frameId;
      option.textContent = `#${frame.frameId} ${frame.url || '(about:blank)'}`;
      elements.frameSelector.appendChild(option);
    });

    elements.frameSelector.value = "0";
    currentFrameId = 0;
  } catch (error) {
    console.error('获取框架列表失败:', error);
  }
}

// 检查content script状态
async function checkContentScriptStatus() {
  const response = await sendMessageToContent({
    type: "get_page_info"
  });

  if (response?.ok) {
    return true;
  }
  return false;
}

// 防抖变量
let renderInProgress = false;

// 渲染DOM树 - 优化版本
async function renderDomTree() {
  // 防止重复渲染
  if (renderInProgress) {
    console.log('[DOM树] 渲染正在进行中，跳过重复请求');
    return;
  }

  renderInProgress = true;
  console.log('[DOM树] 开始渲染');

  try {
    elements.treeContainer.innerHTML = '<div class="loading">检查页面状态...</div>';

    // 首先检查content script是否已加载
    const isScriptLoaded = await checkContentScriptStatus();
    if (!isScriptLoaded) {
      elements.treeContainer.innerHTML = `
        <div class="empty-state">
          <div style="margin-bottom: 15px; font-size: 14px; color: #dc2626;">🔌 需要初始化插件</div>
          <div style="font-size: 12px; color: #6b7280; margin-bottom: 15px; line-height: 1.5;">
            点击下方按钮初始化content script，然后刷新DOM树
          </div>
          <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin: 10px 0; font-size: 11px;">
            <div style="font-weight: 600; margin-bottom: 5px;">可能的原因：</div>
            <div style="color: #6b7280;">• 页面刚刚加载，content script还未就绪</div>
            <div style="color: #6b7280;">• 页面使用了复杂的安全策略</div>
            <div style="color: #6b7280;">• 浏览器扩展权限限制</div>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 15px;">
            <button id="initBtn" class="btn primary">初始化插件</button>
            <button id="retryBtn" class="btn">重试DOM树</button>
          </div>
        </div>
      `;

      // 添加初始化按钮事件
      const initBtn = document.getElementById('initBtn');
      if (initBtn) {
        initBtn.onclick = async () => {
          initBtn.textContent = '初始化中...';
          initBtn.disabled = true;

          const success = await tryInjectContentScript();
          if (success) {
            initBtn.textContent = '✓ 初始化成功';
            setTimeout(() => {
              renderInProgress = false;
              renderDomTree();
            }, 1000);
          } else {
            initBtn.textContent = '✗ 初始化失败';
            initBtn.disabled = false;
          }
        };
      }

      // 添加重试按钮事件
      const retryBtn = document.getElementById('retryBtn');
      if (retryBtn) {
        retryBtn.onclick = () => {
          renderInProgress = false;
          renderDomTree();
        };
      }

      return;
    }

    elements.treeContainer.innerHTML = '<div class="loading">加载DOM树中...</div>';

    const response = await sendMessageToContent({
      type: "dom_snapshot",
      maxDepth: 15,    // 增加深度到15层
      maxChildren: 2000 // 增加节点数到2000个
    });

    if (!response?.ok) {
      elements.treeContainer.innerHTML = '<div class="empty-state">无法读取DOM（此页面可能禁止注入）</div>';
      return;
    }

    const root = response.tree;

    // 获取过滤文本（移到这里避免作用域错误）
    const filterText = (elements.filterInput.value || "").trim().toLowerCase();

    // 添加调试信息
    console.log('DOM树加载完成:', {
      rootTag: root?.tag,
      totalChildren: countTotalNodes(root),
      maxDepth: calculateMaxDepth(root),
      url: currentUrl,
      filterText: filterText
    });

    // 在界面上显示一些统计信息
    const totalNodes = countTotalNodes(root);
    const visibleNodes = countRenderedNodes(root, filterText);
    const maxDepth = calculateMaxDepth(root);
    const stats = document.createElement('div');
    stats.style.cssText = 'font-size: 11px; color: #6b7280; margin-bottom: 8px; padding: 4px; background: #f9fafb; border-radius: 4px;';

    // 节点数量警告
    let nodeWarning = '';
    if (visibleNodes > 5000) {
      nodeWarning = ' <span style="color: #ef4444;">⚠️ 节点过多，可能影响性能</span>';
    } else if (visibleNodes > 2000) {
      nodeWarning = ' <span style="color: #f59e0b;">⚠️ 节点较多</span>';
    }

    stats.innerHTML = `
      <strong>页面统计:</strong>
      可见节点: <span style="color: #4f46e5; font-weight: 600;">${visibleNodes}</span>${nodeWarning} |
      总节点数: <span style="color: #6b7280; font-weight: 600;">${totalNodes}</span> |
      最大深度: <span style="color: #4f46e5; font-weight: 600;">${maxDepth}</span> |
      当前URL: <span style="color: #4f46e5;">${new URL(currentUrl).hostname}</span>
    `;

    elements.treeContainer.innerHTML = '';
    elements.treeContainer.appendChild(stats);

    const treeElement = document.createElement('div');
    treeElement.className = 'tree';
    elements.treeContainer.appendChild(treeElement);

    const ul = document.createElement('ul');
    treeElement.appendChild(ul);

    // 使用改进的分批渲染
    await renderBatchNodes(root, ul, filterText);

    console.log(`DOM树渲染完成，共渲染 ${countRenderedNodes(root, filterText)} 个可见节点`);

  } catch (error) {
    console.error('[DOM树] 渲染过程中出错:', error);
    console.error('[DOM树] 错误堆栈:', error.stack);
    elements.treeContainer.innerHTML = `<div class="empty-state">渲染DOM树时出错: ${error.message}</div>`;

    // 显示更详细的错误信息和重试按钮
    elements.treeContainer.innerHTML += `
      <div style="margin-top: 15px; padding: 10px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px;">
        <div style="font-weight: 600; margin-bottom: 5px;">错误详情:</div>
        <div style="font-family: monospace; font-size: 11px; color: #dc2626; white-space: pre-wrap;">${error.stack}</div>
        <button id="retryAfterError" class="btn primary" style="margin-top: 10px;">重试渲染</button>
      </div>
    `;

    // 添加重试按钮事件
    const retryBtn = document.getElementById('retryAfterError');
    if (retryBtn) {
      retryBtn.onclick = () => {
        renderInProgress = false;
        renderDomTree();
      };
    }
  } finally {
    renderInProgress = false;
    console.log('[DOM树] 渲染完成');
  }
}

// 统计节点总数
function countTotalNodes(node) {
  if (!node) return 0;
  let count = 1;
  if (node.children) {
    for (const child of node.children) {
      count += countTotalNodes(child);
    }
  }
  return count;
}

// 计算最大深度
function calculateMaxDepth(node, currentDepth = 0) {
  if (!node || !node.children || node.children.length === 0) return currentDepth;

  let maxChildDepth = currentDepth;
  for (const child of node.children) {
    const childDepth = calculateMaxDepth(child, currentDepth + 1);
    maxChildDepth = Math.max(maxChildDepth, childDepth);
  }
  return maxChildDepth;
}

// 统计可见节点数量
function countRenderedNodes(node, filterText, depth = 0) {
  if (!node || !shouldDisplayNode(node)) return 0;

  let count = matchesFilter(node, filterText) ? 1 : 0;

  if (node.children && !node.collapsed) {
    for (const child of node.children) {
      count += countRenderedNodes(child, filterText, depth + 1);
    }
  }

  return count;
}

// 检查节点是否匹配过滤条件 - 支持文本内容、value属性等
function matchesFilter(node, filterText) {
  if (!filterText || !filterText.trim()) return true;

  const searchText = filterText.toLowerCase();

  // 1. 检查标签名
  if (node.tag && node.tag.toLowerCase().includes(searchText)) return true;

  // 2. 检查inner text - 优先搜索文本内容
  if (node.text && node.text.trim()) {
    const cleanText = node.text.trim().toLowerCase();
    if (cleanText.includes(searchText)) return true;
  }

  // 3. 检查value属性 - 特别重要对于input、select等元素
  if (node.attributes) {
    // 优先检查value属性
    if (node.attributes.value) {
      const value = String(node.attributes.value).toLowerCase();
      if (value.includes(searchText)) return true;
    }

    // 检查placeholder属性
    if (node.attributes.placeholder) {
      const placeholder = String(node.attributes.placeholder).toLowerCase();
      if (placeholder.includes(searchText)) return true;
    }

    // 检查title属性
    if (node.attributes.title) {
      const title = String(node.attributes.title).toLowerCase();
      if (title.includes(searchText)) return true;
    }

    // 检查name属性
    if (node.attributes.name) {
      const name = String(node.attributes.name).toLowerCase();
      if (name.includes(searchText)) return true;
    }

    // 检查id和class属性
    if (node.attributes.id) {
      const id = String(node.attributes.id).toLowerCase();
      if (id.includes(searchText)) return true;
    }

    if (node.attributes.class) {
      const classes = String(node.attributes.class).toLowerCase();
      if (classes.includes(searchText)) return true;
    }

    // 检查其他常见属性
    for (const [key, value] of Object.entries(node.attributes)) {
      const keyLower = key.toLowerCase();
      const valueLower = String(value).toLowerCase();

      // 搜索属性名
      if (keyLower.includes(searchText)) return true;

      // 搜索属性值（排除已检查的属性以避免重复）
      if (!['value', 'placeholder', 'title', 'name', 'id', 'class'].includes(keyLower) &&
          valueLower.includes(searchText)) {
        return true;
      }
    }
  }

  return false;
}

// 检查节点是否应该显示（过滤掉script等不相关节点）
function shouldDisplayNode(node) {
  if (!node || !node.tag) return false;

  // 忽略的节点类型，与content-script.js保持一致
  const ignoredTags = ['script', 'style', 'link', 'meta', 'noscript'];
  return !ignoredTags.includes(node.tag.toLowerCase());
}

// 分批渲染节点 - 优化版本
async function renderBatchNodes(root, rootUl, filterText) {
  const batchSize = 100; // 增加批处理大小

  // 直接使用递归渲染，但加入性能优化
  await renderNodeOptimized(root, rootUl, 0, filterText);
}

// 优化的递归渲染单个节点
async function renderNodeOptimized(node, parentUl, depth = 0, filterText = '') {
  if (!node || !shouldDisplayNode(node)) return;

  const show = matchesFilter(node, filterText);
  if (!show && !hasVisibleChildren(node, filterText)) return; // 如果不匹配且没有可见子节点，则跳过

  const li = document.createElement('li');
  li.dataset.cssPath = node.cssPath || '';
  li.dataset.depth = depth.toString();

  const nodeContainer = document.createElement('div');
  nodeContainer.style.display = 'flex';
  nodeContainer.style.alignItems = 'center';
  nodeContainer.style.gap = '4px';

  // 添加折叠/展开按钮
  if (node.hasChildren && node.childrenCount > 0) {
    const toggleBtn = document.createElement('span');
    toggleBtn.className = 'toggle-btn';
    toggleBtn.textContent = node.collapsed ? '▶' : '▼';
    toggleBtn.style.cursor = 'pointer';
    toggleBtn.style.fontSize = '10px';
    toggleBtn.style.width = '12px';
    toggleBtn.style.display = 'inline-block';
    toggleBtn.style.userSelect = 'none';

    toggleBtn.onclick = async (e) => {
      e.stopPropagation();
      await toggleNode(node, toggleBtn, li, depth);
    };

    nodeContainer.appendChild(toggleBtn);
  } else {
    // 占位符
    const spacer = document.createElement('span');
    spacer.style.width = '12px';
    spacer.style.display = 'inline-block';
    nodeContainer.appendChild(spacer);
  }

  const span = document.createElement('span');
  span.className = 'node';

  let nodeHtml = `<span class="tag">&lt;${node.tag}&gt;</span>`;

  // 显示重要属性
  if (node.attributes && Object.keys(node.attributes).length > 0) {
    const attrs = [];
    for (const [key, value] of Object.entries(node.attributes)) {
      if (key === 'id') {
        attrs.push(`<span class="id">#${escapeHtml(value)}</span>`);
      } else if (key === 'class') {
        const classes = value.trim().split(/\s+/).slice(0, 2).map(cls => `.${escapeHtml(cls)}`).join('');
        attrs.push(`<span class="class">${classes}${value.trim().split(/\s+/).length > 2 ? '...' : ''}</span>`);
      } else if (key === 'data-testid' || key === 'data-qa') {
        attrs.push(`<span class="test-id">[${key}="${escapeHtml(value)}"]</span>`);
      } else if (key === 'aria-label' || key === 'title') {
        attrs.push(`<span class="aria">[${key}="${escapeHtml(value.slice(0, 20))}${value.length > 20 ? '...' : ''}"]</span>`);
      } else if (key === 'href' || key === 'src') {
        attrs.push(`<span class="link">${key}="..."</span>`);
      } else if (key === 'placeholder' || key === 'type' || key === 'name') {
        attrs.push(`<span class="input-attr">${key}="${escapeHtml(value)}"</span>`);
      }
    }
    nodeHtml += ' ' + attrs.join(' ');
  }

  // 显示文本内容
  if (node.text) {
    nodeHtml += ` <span class="text">"${escapeHtml(node.text)}"</span>`;
  }

  span.innerHTML = nodeHtml;
  span.style.flex = '1';

  // 单击事件：高亮元素（添加防抖）
  let clickTimeout = null;
  span.onclick = async () => {
    clearTimeout(clickTimeout);
    clickTimeout = setTimeout(async () => {
      try {
        await sendMessageToContent({ type: "highlight_by_css", cssPath: node.cssPath });
      } catch (error) {
        console.error('高亮元素失败:', error);
      }
    }, 200);
  };

  // 双击事件：添加标注（需要与单击事件配合使用）
  span.ondblclick = async () => {
    clearTimeout(clickTimeout); // 取消单击事件
    try {
      await sendMessageToContent({ type: "mark_by_css", cssPath: node.cssPath });
      await renderMarksList();
    } catch (error) {
      console.error('添加标注失败:', error);
    }
  };

  nodeContainer.appendChild(span);
  li.appendChild(nodeContainer);

  // 创建子节点容器
  if (node.hasChildren) {
    const childUl = document.createElement('ul');
    childUl.style.display = node.collapsed ? 'none' : 'block';
    childUl.className = 'children-ul';

    // 如果子节点已加载，直接渲染
    if (node.childrenLoaded && node.children && node.children.length > 0) {
      // 分批渲染子节点以避免阻塞
      const children = node.children;
      for (let i = 0; i < children.length; i++) {
        await renderNodeOptimized(children[i], childUl, depth + 1, filterText);

        // 每渲染10个节点让出一次控制权
        if (i % 10 === 0) {
          await new Promise(resolve => setTimeout(resolve, 0));
        }
      }
    }

    li.appendChild(childUl);
  }

  // 只有匹配过滤条件或有可见子节点的才添加到DOM
  if (show || hasVisibleChildren(node, filterText)) {
    parentUl.appendChild(li);
  }
}

// 检查节点是否有可见的子节点
function hasVisibleChildren(node, filterText) {
  if (!node.children || node.collapsed) return false;

  return node.children.some(child =>
    shouldDisplayNode(child) && (matchesFilter(child, filterText) || hasVisibleChildren(child, filterText))
  );
}

// 切换节点折叠状态 - 优化版本
async function toggleNode(node, toggleBtn, li, depth) {
  console.log(`[懒加载] 切换节点: ${node.tag}, 深度: ${depth}, 已加载: ${node.childrenLoaded}, 折叠状态: ${node.collapsed}`);

  node.collapsed = !node.collapsed;
  toggleBtn.textContent = node.collapsed ? '▶' : '▼';

  const childUl = li.querySelector('.children-ul');
  if (childUl) {
    if (node.collapsed) {
      console.log(`[懒加载] 折叠节点: ${node.tag}`);
      childUl.style.display = 'none';
    } else {
      console.log(`[懒加载] 展开节点: ${node.tag}`);
      // 如果子节点未加载，懒加载
      if (!node.childrenLoaded && node.cssPath) {
        console.log(`[懒加载] 开始懒加载子节点: ${node.tag}, CSS路径: ${node.cssPath}`);
        try {
          toggleBtn.textContent = '⏳';

          const response = await sendMessageToContent({
            type: "load_children",
            cssPath: node.cssPath,
            depth: depth,
            maxDepth: 15,
            maxChildren: 200
          });

          console.log(`[懒加载] 收到响应:`, response);

          if (response?.ok && response.children && Array.isArray(response.children)) {
            console.log(`[懒加载] 成功加载 ${response.children.length} 个子节点`);

            // 更新节点的childrenLoaded状态
            node.childrenLoaded = true;
            node.collapsed = false;

            // 清空现有子节点
            childUl.innerHTML = '';

            // 渲染新加载的子节点
            const filterText = (elements.filterInput.value || "").trim().toLowerCase();
            for (const child of response.children) {
              await renderNodeOptimized(child, childUl, depth + 1, filterText);
            }
            console.log(`[懒加载] 子节点渲染完成`);

            // 更新toggle按钮状态
            toggleBtn.textContent = '▼';
          } else {
            console.log(`[懒加载] 响应无效或无子节点:`, response);
            // 如果懒加载失败，重置按钮状态
            toggleBtn.textContent = '▶';
            node.collapsed = true;
          }
        } catch (error) {
          console.error('[懒加载] 懒加载子节点失败:', error);
          toggleBtn.textContent = '▶';
          node.collapsed = true;
        }
      } else {
        console.log(`[懒加载] 子节点已加载，直接展开`);
      }
      childUl.style.display = 'block';
    }
  }
}

// 渲染标注列表 - 页面级别管理
async function renderMarksList() {
  const response = await chrome.runtime.sendMessage({ type: "get_marks" });
  allMarks = response?.data || {};

  const pageKey = normalizePageUrl(currentUrl);
  const pageMarks = allMarks[pageKey] || [];

  elements.marksList.innerHTML = '';

  // 显示当前页面信息
  const pageInfo = document.createElement('div');
  pageInfo.style.cssText = 'padding: 8px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 12px; font-size: 12px;';
  pageInfo.innerHTML = `
    <div style="font-weight: 600; color: #475569; margin-bottom: 4px;">当前页面</div>
    <div style="color: #64748b; word-break: break-all;">${currentUrl}</div>
    <div style="color: #475569; margin-top: 4px;">标注数量: <span style="font-weight: 600; color: #2563eb;">${pageMarks.length}</span></div>
  `;
  elements.marksList.appendChild(pageInfo);

  if (pageMarks.length === 0) {
    const emptyState = document.createElement('div');
    emptyState.className = 'empty-state';
    emptyState.innerHTML = `
      <div style="margin-bottom: 8px;">🎯 当前页面暂无标注</div>
      <div style="font-size: 11px; color: #6b7280; line-height: 1.4;">
        • 开启标注模式（Alt+P）<br>
        • 直接点击页面元素<br>
        • 或在左侧DOM树中双击节点
      </div>
    `;
    elements.marksList.appendChild(emptyState);
    return;
  }

  // 渲染标注列表
  const marksContainer = document.createElement('div');
  marksContainer.className = 'marks-container';

  pageMarks.forEach((mark, index) => {
    const markElement = document.createElement('div');
    markElement.className = 'mark-item';

    const tag = mark.fingerprint?.tag || '';
    const id = mark.fingerprint?.id || '';
    const testId = mark.fingerprint?.['data-testid'] || '';
    const text = mark.fingerprint?.text || '';
    const candidates = mark.candidates || [];

    // 生成元素指纹显示
    let fingerprintDisplay = tag;
    if (id) fingerprintDisplay += ` #${escapeHtml(id)}`;
    if (testId) fingerprintDisplay += ` [${escapeHtml(testId)}]`;
    if (text && text.length < 20) fingerprintDisplay += ` "${escapeHtml(text)}"`;

    markElement.innerHTML = `
      <div class="mark-fingerprint">
        ${fingerprintDisplay}
      </div>
      <div class="candidates">
        <div style="font-size: 10px; color: #6b7280; margin-bottom: 4px;">候选选择器:</div>
        ${candidates.slice(0, 2).map(c => `<code class="selector-code">${escapeHtml(c)}</code>`).join(' ')}
        ${candidates.length > 2 ? `<div style="font-size: 10px; color: #6b7280; margin-top: 4px;">还有 ${candidates.length - 2} 个候选选择器</div>` : ''}
      </div>
      <textarea data-index="${index}" placeholder="添加描述（可选）..." rows="2">${mark.desc || ''}</textarea>
      <div class="actions">
        <button class="btn" data-action="highlight" data-index="${index}" title="在页面中高亮此元素">
          🔍 高亮
        </button>
        <button class="btn danger" data-action="remove" data-index="${index}" title="删除此标注">
          🗑️ 删除
        </button>
      </div>
    `;

    marksContainer.appendChild(markElement);
  });

  elements.marksList.appendChild(marksContainer);

  // 绑定事件监听器
  elements.marksList.querySelectorAll('textarea').forEach(textarea => {
    textarea.onchange = async (event) => {
      const index = Number(event.target.dataset.index);
      const description = event.target.value;
      await chrome.runtime.sendMessage({
        type: "update_mark_description",
        url: currentUrl,
        index: index,
        description: description
      });
    };
  });

  elements.marksList.querySelectorAll('button').forEach(button => {
    button.onclick = async (event) => {
      const action = event.target.dataset.action;
      const index = Number(event.target.dataset.index);

      if (action === 'highlight') {
        const mark = pageMarks[index];
        if (mark?.cssPath) {
          await sendMessageToContent({ type: "highlight_by_css", cssPath: mark.cssPath });
        }
      } else if (action === 'remove') {
        if (confirm('确定要删除这个标注吗？')) {
          await chrome.runtime.sendMessage({
            type: "remove_mark",
            url: currentUrl,
            index: index
          });
          await renderMarksList();
        }
      }
    };
  });
}

// 切换标注模式
async function togglePickingMode() {
  isPickingMode = !isPickingMode;

  await sendMessageToContent({ type: "toggle_picking_mode", on: isPickingMode });

  elements.toggleMode.textContent = isPickingMode ? '关闭标注' : '开启标注';
  elements.toggleMode.classList.toggle('active', isPickingMode);
}

// 导出当前页面标注数据 - 符合site_profiles格式
async function exportMarks() {
  try {
    elements.exportBtn.disabled = true;
    elements.exportBtn.textContent = '导出中...';

    const response = await chrome.runtime.sendMessage({
      type: "download_export",
      currentUrl: currentUrl
    });

    if (response?.ok) {
      console.log('导出成功:', response.filename);
    } else {
      throw new Error(response?.error || '导出失败');
    }
  } catch (error) {
    console.error('导出失败:', error);
    alert('导出失败: ' + error.message);
  } finally {
    elements.exportBtn.disabled = false;
    elements.exportBtn.textContent = '导出';
  }
}

// 清空当前页标注
async function clearCurrentPageMarks() {
  if (!confirm('确定要清空当前页面的所有标注吗？此操作不可恢复。')) {
    return;
  }

  await chrome.runtime.sendMessage({
    type: "clear_marks_by_url",
    url: currentUrl
  });

  await renderMarksList();
}

// 初始化应用
async function initialize() {
  try {
    console.log('开始初始化侧边面板...');

    // 首先初始化DOM元素引用
    initializeElements();
    console.log('DOM元素初始化完成');

    const tab = await getActiveTab();
    if (!tab) {
      console.warn('无法获取当前活动标签页');
      if (elements.currentUrl) {
        elements.currentUrl.textContent = '无法获取当前页面信息';
      }
      return;
    }

    currentTabId = tab.id;
    currentUrl = tab.url || "";
    elements.currentUrl.textContent = currentUrl;
    elements.currentUrl.title = currentUrl;
    console.log('当前页面:', currentUrl);

    await initializeFrameSelector();
    await renderDomTree();
    await renderMarksList();

    // 绑定事件监听器
    bindEventListeners();
    console.log('侧边面板初始化完成');
  } catch (error) {
    console.error('初始化过程中发生错误:', error);
    if (elements.currentUrl) {
      elements.currentUrl.textContent = `初始化失败: ${error.message}`;
    }
  }
}

// 绑定事件监听器 - 延迟到元素初始化后执行
function bindEventListeners() {
  try {
    console.log('开始绑定事件监听器...');

    // 验证核心元素是否存在
    const coreElements = ['toggleMode', 'exportBtn', 'treeContainer', 'marksList'];
    const missingElements = coreElements.filter(id => !elements[id]);

    if (missingElements.length > 0) {
      console.error('核心DOM元素缺失，无法绑定事件:', missingElements);
      return;
    }

    let boundCount = 0;

    // 核心功能按钮事件
    if (elements.toggleMode) {
      elements.toggleMode.onclick = togglePickingMode;
      boundCount++;
    }

    if (elements.refreshTree) {
      elements.refreshTree.onclick = renderDomTree;
      boundCount++;
    }

    if (elements.filterInput) {
      elements.filterInput.oninput = renderDomTree;
      boundCount++;
    }

    if (elements.exportBtn) {
      elements.exportBtn.onclick = exportMarks;
      boundCount++;
    }

    if (elements.clearBtn) {
      elements.clearBtn.onclick = clearCurrentPageMarks;
      boundCount++;
    }

    // 框架选择器事件（如果存在）
    if (elements.frameSelector) {
      elements.frameSelector.onchange = async (event) => {
        currentFrameId = Number(event.target.value || 0);
        await renderDomTree();
      };
      boundCount++;
    }

    console.log(`事件绑定完成，共绑定 ${boundCount} 个事件处理器`);
  } catch (error) {
    console.error('绑定事件监听器时发生错误:', error);
  }
}

// 不需要的按钮处理器函数已移除

// 事件绑定已移至 bindEventListeners() 函数中，确保在DOM元素加载完成后执行


// 监听来自background的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "picking_mode_changed") {
    isPickingMode = message.picking;
    elements.toggleMode.textContent = isPickingMode ? '关闭标注' : '开启标注';
    elements.toggleMode.classList.toggle('active', isPickingMode);
  }
});

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
  console.log('DOMContentLoaded 事件触发，开始初始化...');
  initialize().catch(error => {
    console.error('初始化失败:', error);
    // 尝试在界面上显示错误信息
    const urlElement = document.getElementById('currentUrl');
    if (urlElement) {
      urlElement.textContent = `初始化失败: ${error.message}`;
    }
  });
});

// 监听标签页更新
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tabId === currentTabId && changeInfo.status === 'complete') {
    currentUrl = tab.url || "";
    elements.currentUrl.textContent = currentUrl;
    elements.currentUrl.title = currentUrl;

    setTimeout(() => {
      renderDomTree();
      renderMarksList();
    }, 1000); // 延迟一秒等待页面加载完成
  }
});