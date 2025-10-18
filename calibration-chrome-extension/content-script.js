/**
 * Content Script: 页面元素打标功能
 * 负责overlay高亮、标注模式、DOM快照、元素选择器生成
 */

let picking = false;
let overlayEl = null;
let lastHighlighted = null;

// 初始化overlay元素
function ensureOverlay() {
  if (overlayEl) return overlayEl;
  overlayEl = document.createElement('div');
  overlayEl.id = '__calib_overlay__';
  document.documentElement.appendChild(overlayEl);
  return overlayEl;
}

// 高亮元素 - 增强版本
function highlightElement(element) {
  ensureOverlay();
  if (!element || !element.getBoundingClientRect) return;

  try {
    // 移除之前的高亮
    clearHighlight();

    const rect = element.getBoundingClientRect();
    const highlightBox = document.createElement('div');
    highlightBox.className = '__calib_box';

    // 考虑设备像素比和滚动位置
    const scrollX = window.scrollX || window.pageXOffset;
    const scrollY = window.scrollY || window.pageYOffset;
    const dpr = window.devicePixelRatio || 1;

    // 设置高亮框位置和大小
    highlightBox.style.left = (rect.left + scrollX) + 'px';
    highlightBox.style.top = (rect.top + scrollY) + 'px';
    highlightBox.style.width = rect.width + 'px';
    highlightBox.style.height = rect.height + 'px';

    // 添加调试信息
    highlightBox.title = `元素: ${element.tagName.toLowerCase()}${element.id ? '#' + element.id : ''}${element.className ? '.' + element.className.split(' ').join('.') : ''}\n位置: (${Math.round(rect.left)}, ${Math.round(rect.top)})\n大小: ${Math.round(rect.width)}x${Math.round(rect.height)}`;

    overlayEl.appendChild(highlightBox);
    lastHighlighted = element;

    console.log(`[Content Script] 高亮元素:`, {
      tag: element.tagName.toLowerCase(),
      id: element.id,
      class: element.className,
      rect: {
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height
      },
      scrollPosition: { x: scrollX, y: scrollY },
      dpr: dpr
    });

  } catch (error) {
    console.error('[Content Script] 高亮元素失败:', error);
    clearHighlight();
  }
}

// 清除高亮
function clearHighlight() {
  if (overlayEl) {
    overlayEl.innerHTML = '';
  }
  lastHighlighted = null;
}

// 显示操作提示
function showTip(text = '✓ 已记录') {
  const tip = document.createElement('div');
  tip.className = '__calib_tip';
  tip.textContent = text;
  document.documentElement.appendChild(tip);
  setTimeout(() => tip.remove(), 600);
}

// 生成元素指纹信息
function generateFingerprint(element) {
  const attrs = ["id", "name", "data-testid", "data-qa", "role", "aria-label", "title"];
  const fingerprint = {
    tag: (element.tagName || '').toLowerCase()
  };

  for (const attr of attrs) {
    const value = element.getAttribute?.(attr);
    if (value) fingerprint[attr] = value;
  }

  const text = (element.textContent || "").replace(/\s+/g, ' ').trim();
  if (text) fingerprint.text = text.slice(0, 120);

  return fingerprint;
}

// 生成CSS候选选择器 - 增强版本
function generateCssCandidates(element) {
  const candidates = [];

  try {
    // 优先级1: ID选择器（如果ID是唯一的）
    if (element.id && element.id.trim()) {
      const idSelector = `#${CSS.escape(element.id)}`;
      // 检查ID是否唯一
      const sameIdElements = document.querySelectorAll(idSelector);
      if (sameIdElements.length === 1) {
        candidates.push({
          selector: idSelector,
          priority: 1,
          uniqueness: 1.0,
          type: 'id'
        });
      } else {
        candidates.push({
          selector: idSelector,
          priority: 1,
          uniqueness: 1.0 / sameIdElements.length,
          type: 'id'
        });
      }
    }

    // 优先级2: 测试属性选择器
    const testId = element.getAttribute?.("data-testid");
    if (testId && testId.trim()) {
      const testSelector = `[data-testid="${CSS.escape(testId)}"]`;
      const sameTestElements = document.querySelectorAll(testSelector);
      candidates.push({
        selector: testSelector,
        priority: 2,
        uniqueness: 1.0 / sameTestElements.length,
        type: 'test-id'
      });
    }

    // 优先级3: ARIA标签选择器
    const ariaLabel = element.getAttribute?.("aria-label");
    if (ariaLabel && ariaLabel.trim()) {
      const ariaSelector = `[aria-label="${CSS.escape(ariaLabel)}"]`;
      const sameAriaElements = document.querySelectorAll(ariaSelector);
      candidates.push({
        selector: ariaSelector,
        priority: 3,
        uniqueness: 1.0 / sameAriaElements.length,
        type: 'aria-label'
      });
    }

    // 优先级4: 类选择器（选择主要的类）
    if (element.className && typeof element.className === 'string') {
      const classes = element.className.trim().split(/\s+/).filter(cls => cls.length > 0);
      if (classes.length > 0) {
        // 选择前1-2个最有意义的类名
        const mainClasses = classes.slice(0, 2);
        const classSelector = `${element.tagName.toLowerCase()}.${mainClasses.map(cls => CSS.escape(cls)).join('.')}`;
        const sameClassElements = document.querySelectorAll(classSelector);
        candidates.push({
          selector: classSelector,
          priority: 4,
          uniqueness: 1.0 / sameClassElements.length,
          type: 'class'
        });
      }
    }

    // 优先级5: 属性组合选择器
    const importantAttrs = ['name', 'type', 'role', 'placeholder', 'title'];
    const attrParts = [];
    for (const attr of importantAttrs) {
      const value = element.getAttribute?.(attr);
      if (value && value.trim()) {
        attrParts.push(`[${attr}="${CSS.escape(value)}"]`);
      }
    }

    if (attrParts.length > 0) {
      const attrSelector = `${element.tagName.toLowerCase()}${attrParts.join('')}`;
      const sameAttrElements = document.querySelectorAll(attrSelector);
      candidates.push({
        selector: attrSelector,
        priority: 5,
        uniqueness: 1.0 / sameAttrElements.length,
        type: 'attributes'
      });
    }

    // 优先级6: 标签+nth-of-type (备选)
    const parent = element.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(child => child.tagName === element.tagName);
      const index = siblings.indexOf(element) + 1;
      const nthSelector = `${element.tagName.toLowerCase()}:nth-of-type(${index})`;
      candidates.push({
        selector: nthSelector,
        priority: 6,
        uniqueness: 1.0 / siblings.length,
        type: 'nth-of-type'
      });
    }

    // 按优先级和唯一性排序
    candidates.sort((a, b) => {
      if (a.priority !== b.priority) {
        return a.priority - b.priority; // 优先级数字越小越好
      }
      return b.uniqueness - a.uniqueness; // 唯一性越高越好
    });

    // 返回前5个最佳候选选择器
    return candidates.slice(0, 5).map(c => c.selector);

  } catch (error) {
    console.error('[Content Script] 生成CSS选择器失败:', error);
    // 降级为简单的标签选择器
    return [element.tagName.toLowerCase()];
  }
}

// 生成CSS路径 - 增强版本
function generateCssPath(element) {
  const pathParts = [];
  let current = element;
  let depth = 0;
  const maxDepth = 15; // 限制最大深度

  while (current && current.nodeType === 1 && depth < maxDepth) {
    const tagName = current.tagName.toLowerCase();

    // 如果有唯一的ID，直接使用ID作为路径
    if (current.id && current.id.trim()) {
      const idSelector = `#${CSS.escape(current.id)}`;
      const sameIdElements = document.querySelectorAll(idSelector);
      if (sameIdElements.length === 1) {
        pathParts.unshift(idSelector);
        break; // 找到唯一ID，停止向上查找
      }
    }

    // 构建选择器部分
    let selectorPart = tagName;

    // 添加主要类名（最多2个）
    if (current.className && typeof current.className === 'string') {
      const classes = current.className.trim().split(/\s+/).filter(cls => cls.length > 0);
      if (classes.length > 0) {
        const mainClasses = classes.slice(0, 2);
        selectorPart += '.' + mainClasses.map(CSS.escape).join('.');
      }
    }

    // 添加重要属性
    const importantAttrs = ['data-testid', 'data-qa', 'role', 'name', 'type'];
    const attrParts = [];
    for (const attr of importantAttrs) {
      const value = current.getAttribute?.(attr);
      if (value && value.trim()) {
        attrParts.push(`[${attr}="${CSS.escape(value)}"]`);
        // 最多添加2个属性以保持选择器简洁
        if (attrParts.length >= 2) break;
      }
    }
    selectorPart += attrParts.join('');

    // 如果选择器仍然不够具体，添加nth-of-type
    const parent = current.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children).filter(child => child.tagName === current.tagName);
      if (siblings.length > 1) {
        const index = siblings.indexOf(current) + 1;
        selectorPart += `:nth-of-type(${index})`;
      }
    }

    pathParts.unshift(selectorPart);
    current = parent;
    depth++;
  }

  const fullPath = pathParts.join(' > ');

  // 限制路径长度
  if (fullPath.length > 1024) {
    console.warn('[Content Script] CSS路径过长，已截断:', fullPath.length);
    return fullPath.slice(0, 1021) + '...';
  }

  return fullPath;
}

// 构建标注数据
function buildMarkData(element) {
  const rect = element.getBoundingClientRect();
  return {
    url: location.href,
    ts: Date.now(),
    rect: {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      dpr: window.devicePixelRatio
    },
    fingerprint: generateFingerprint(element),
    candidates: generateCssCandidates(element),
    cssPath: generateCssPath(element)
  };
}

// DOM快照序列化（支持懒加载和折叠）
function serializeDomTree(element, depth = 0, maxDepth = 15, maxChildren = 500, parentNode = null) {
  if (!element || depth > maxDepth) return null;

  const tagName = (element.tagName || '').toLowerCase();
  if (!tagName) return null;

  // 忽略script节点和样式相关节点，保持DOM树清洁
  const ignoredTags = ['script', 'style', 'link', 'meta', 'noscript'];
  if (ignoredTags.includes(tagName)) {
    console.log(`[Content Script] 忽略节点: ${tagName}`);
    return null;
  }

  // 收集更多有用的属性
  const attributes = {};
  const importantAttrs = ['id', 'class', 'name', 'data-testid', 'data-qa', 'role', 'aria-label', 'title', 'alt', 'href', 'src', 'type', 'placeholder', 'value'];

  for (const attr of importantAttrs) {
    const value = element.getAttribute?.(attr);
    if (value) attributes[attr] = value;
  }

  // 获取文本内容（限制长度）
  let textContent = '';
  if (element.textContent) {
    textContent = element.textContent.trim().slice(0, 80);
    if (textContent.length === 80) textContent += '...';
  }

  // 过滤掉script标签的子节点
  let children = [];
  if (element.children && element.children.length > 0) {
    children = Array.from(element.children).filter(child => {
      const childTagName = (child.tagName || '').toLowerCase();
      return !ignoredTags.includes(childTagName);
    });
  }

  const hasChildren = children.length > 0;
  const childrenCount = children.length;

  const node = {
    tag: tagName,
    attributes: attributes,
    text: textContent,
    cssPath: generateCssPath(element),
    hasChildren: hasChildren,
    childrenCount: childrenCount,
    collapsed: depth > 6, // 默认折叠深度大于6的节点，允许更多展开
    childrenLoaded: !hasChildren || depth <= 5, // 前6层节点直接加载
    children: []
  };

  // 特殊处理某些重要元素
  if (tagName === 'input' || tagName === 'textarea') {
    attributes.placeholder = element.placeholder || '';
    attributes.type = element.type || '';
    if (element.value) {
      attributes.value = element.value.slice(0, 50);
      if (attributes.value.length === 50) attributes.value += '...';
    }
  }

  // 对于浅层节点或有子节点的元素，预加载子节点
  if (node.childrenLoaded && hasChildren) {
    const childrenLimit = Math.min(maxChildren, childrenCount);
    const filteredChildren = children.slice(0, childrenLimit);

    console.log(`[Content Script] 预加载 ${element.tagName}: 子节点总数=${childrenCount}, 过滤后=${filteredChildren.length}, 限制=${childrenLimit}`);

    for (const child of filteredChildren) {
      const childNode = serializeDomTree(child, depth + 1, maxDepth, maxChildren, node);
      if (childNode) {
        node.children.push(childNode);
        console.log(`[Content Script] 预加载子节点: ${childNode.tag}`);
      }
    }

    // 如果有太多子元素被截断，添加提示
    if (childrenCount > childrenLimit) {
      node.children.push({
        tag: '...',
        attributes: { note: `还有 ${childrenCount - childrenLimit} 个子元素` },
        text: '',
        cssPath: '',
        hasChildren: false,
        childrenCount: 0,
        collapsed: false,
        childrenLoaded: true,
        children: []
      });
    }
  }

  return node;
}

// 通过CSS路径查找元素 - 增强版本
function findByCssPath(path) {
  try {
    if (!path) return null;

    // 处理一些常见的CSS路径问题
    let cleanPath = path.trim();

    // 如果路径包含 > 但没有空格，标准化空格
    cleanPath = cleanPath.replace(/>\s*/g, ' > ');

    // 尝试查找元素
    const element = document.querySelector(cleanPath);

    if (element) {
      console.log(`[Content Script] 成功找到元素: ${cleanPath}`);
      return element;
    }

    // 如果找不到，尝试一些修复策略
    console.log(`[Content Script] 未找到元素，尝试修复路径: ${cleanPath}`);

    // 尝试移除末尾的空格
    const trimmedPath = cleanPath.trim();
    if (trimmedPath !== cleanPath) {
      const fixedElement = document.querySelector(trimmedPath);
      if (fixedElement) {
        console.log(`[Content Script] 修复后找到元素: ${trimmedPath}`);
        return fixedElement;
      }
    }

    console.log(`[Content Script] 最终未找到元素: ${path}`);
    return null;

  } catch (error) {
    console.error(`[Content Script] CSS路径查找错误: ${path}`, error);
    return null;
  }
}

// 鼠标移动事件 - 高亮元素（添加节流优化）
let mouseMoveThrottle = null;
let lastHighlightedElement = null;

document.addEventListener('mousemove', (event) => {
  if (!picking) return;

  // 节流处理，避免过于频繁的更新
  if (mouseMoveThrottle) {
    return;
  }

  mouseMoveThrottle = requestAnimationFrame(() => {
    try {
      const element = document.elementFromPoint(event.clientX, event.clientY);

      // 只有当元素发生变化时才重新高亮
      if (element !== lastHighlightedElement) {
        lastHighlightedElement = element;
        if (element) {
          highlightElement(element);
        } else {
          clearHighlight();
        }
      }
    } catch (error) {
      console.error('[Content Script] 鼠标移动事件处理失败:', error);
    } finally {
      mouseMoveThrottle = null;
    }
  });

}, true);

// 点击事件 - 记录标注
document.addEventListener('click', (event) => {
  if (!picking) return;

  event.preventDefault();
  event.stopPropagation();

  const element = document.elementFromPoint(event.clientX, event.clientY);
  if (!element) return;

  const markData = buildMarkData(element);

  // 通过background script保存数据
  chrome.runtime.sendMessage({
    type: "save_mark",
    url: location.href,
    item: markData
  }, (response) => {
    if (chrome.runtime.lastError) {
      console.error('保存标注失败:', chrome.runtime.lastError);
    }
  });

  showTip();
}, true);

// 快捷键 Alt+P 切换标注模式
document.addEventListener('keydown', (event) => {
  if (event.altKey && event.key === 'p') {
    event.preventDefault();
    togglePickingMode();
  }
});

// 切换标注模式
function togglePickingMode() {
  picking = !picking;
  ensureOverlay();
  overlayEl.style.display = picking ? 'block' : 'none';

  if (!picking) {
    overlayEl.innerHTML = '';
  }

  // 通知侧边面板状态变化
  chrome.runtime.sendMessage({
    type: "picking_mode_changed",
    picking: picking
  });
}

// 处理来自侧边面板的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  try {
    if (message?.type === "toggle_picking_mode") {
      picking = !!message.on;
      ensureOverlay();
      overlayEl.style.display = picking ? 'block' : 'none';
      if (!picking) overlayEl.innerHTML = '';
      sendResponse({ ok: true, picking });
    }
    else if (message?.type === "dom_snapshot") {
      const root = serializeDomTree(
        document.documentElement,
        0,
        message.maxDepth ?? 15,
        message.maxChildren ?? 500
      );
      sendResponse({ ok: true, tree: root });
    }
    else if (message?.type === "load_children") {
      // 懒加载子节点
      console.log(`[Content Script] 懒加载请求: CSS路径=${message.cssPath}, 深度=${message.depth}`);
      const element = findByCssPath(message.cssPath);
      if (element && element.children) {
        // 忽略script节点和样式相关节点
        const ignoredTags = ['script', 'style', 'link', 'meta', 'noscript'];
        const filteredChildren = Array.from(element.children).filter(child => {
          const childTagName = (child.tagName || '').toLowerCase();
          return !ignoredTags.includes(childTagName);
        });

        console.log(`[Content Script] 找到元素，原始子元素数量: ${element.children.length}, 过滤后: ${filteredChildren.length}`);
        const children = [];
        const childrenLimit = Math.min(message.maxChildren ?? 50, filteredChildren.length);

        console.log(`[Content Script] 将序列化 ${childrenLimit} 个子元素`);

        for (let i = 0; i < childrenLimit; i++) {
          const child = filteredChildren[i];
          const childNode = serializeDomTree(child, message.depth + 1, message.maxDepth, message.maxChildren);
          if (childNode) {
            children.push(childNode);
            console.log(`[Content Script] 序列化子节点 ${i+1}/${childrenLimit}: ${childNode.tag}`);
          }
        }

        // 如果有更多子元素
        if (filteredChildren.length > childrenLimit) {
          console.log(`[Content Script] 添加截断提示，还有 ${filteredChildren.length - childrenLimit} 个子元素`);
          children.push({
            tag: '...',
            attributes: { note: `还有 ${filteredChildren.length - childrenLimit} 个子元素` },
            text: '',
            cssPath: '',
            hasChildren: false,
            childrenCount: 0,
            collapsed: false,
            childrenLoaded: true,
            children: []
          });
        }

        console.log(`[Content Script] 懒加载完成，返回 ${children.length} 个子节点`);
        sendResponse({ ok: true, children: children });
      } else {
        console.log(`[Content Script] 未找到元素或无子元素:`, { element: !!element, children: element?.children?.length });
        sendResponse({ ok: false, error: "无子元素" });
      }
    }
    else if (message?.type === "highlight_by_css") {
      const element = findByCssPath(message.cssPath);
      if (element) {
        highlightElement(element);
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: "未找到元素" });
      }
    }
    else if (message?.type === "mark_by_css") {
      const element = findByCssPath(message.cssPath);
      if (element) {
        const markData = buildMarkData(element);
        chrome.runtime.sendMessage({
          type: "save_mark",
          url: location.href,
          item: markData
        }, () => {});
        highlightElement(element);
        showTip();
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: "未找到元素" });
      }
    }
    else if (message?.type === "get_page_info") {
      sendResponse({
        ok: true,
        url: location.href,
        title: document.title
      });
    }
  } catch (error) {
    sendResponse({
      ok: false,
      error: String(error)
    });
  }
  return true; // 保持消息通道开启
});

// 标记content script已安装
if (typeof window !== 'undefined') {
  window.__calibration_tool_installed = true;
}

// 页面加载完成时初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    console.log('标定工具 content script 已加载');
  });
} else {
  console.log('标定工具 content script 已加载');
}