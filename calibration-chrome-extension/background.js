/**
 * Background Service Worker: 标定工具后台服务
 * 负责本地存储汇总、消息路由、数据管理
 */

const STORAGE_KEY = "calibration_marks";

// 标准化页面URL（去除query和hash）
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

// 消息监听器
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message?.type) {
        case "save_mark":
          await saveMark(message.url, message.item);
          sendResponse({ ok: true });
          break;

        case "get_marks":
          const marks = await getMarks();
          sendResponse({ ok: true, data: marks });
          break;

        case "get_marks_by_url":
          const urlMarks = await getMarksByUrl(message.url);
          sendResponse({ ok: true, data: urlMarks });
          break;

        case "clear_all_marks":
          await clearAllMarks();
          sendResponse({ ok: true });
          break;

        case "clear_marks_by_url":
          await clearMarksByUrl(message.url);
          sendResponse({ ok: true });
          break;

        case "remove_mark":
          await removeMark(message.url, message.index);
          sendResponse({ ok: true });
          break;

        case "update_mark_description":
          await updateMarkDescription(message.url, message.index, message.description);
          sendResponse({ ok: true });
          break;

        case "download_export":
          const exportData = await prepareExportData(message.currentUrl);

          // 生成符合site_profiles格式的文件名
          const domain = extractDomain(message.currentUrl);
          const urlObj = new URL(message.currentUrl);
          const pagePath = urlObj.pathname.replace(/[^a-zA-Z0-9]/g, '_') || 'home';
          const filename = `${domain}-${pagePath}.json`;

          // 在Service Worker中创建Blob和下载
          const blob = new Blob([JSON.stringify(exportData, null, 2)], {
            type: "application/json"
          });

          // 使用Data URL而不是Blob URL，因为在Service Worker中Blob URL支持有限
          const reader = new FileReader();
          reader.onload = async () => {
            const dataUrl = reader.result;

            try {
              await chrome.downloads.download({
                url: dataUrl,
                filename: filename,
                saveAs: true
              });

              console.log(`成功导出site_profile文件: ${filename}`);
              sendResponse({ ok: true, filename: filename });
            } catch (downloadError) {
              console.error('下载失败:', downloadError);
              sendResponse({ ok: false, error: String(downloadError) });
            }
          };

          reader.onerror = () => {
            console.error('读取Blob失败');
            sendResponse({ ok: false, error: "读取导出数据失败" });
          };

          reader.readAsDataURL(blob);
          break;

        default:
          sendResponse({ ok: false, error: "未知消息类型" });
      }
    } catch (error) {
      console.error('Background处理消息错误:', error);
      sendResponse({ ok: false, error: String(error) });
    }
  })();

  // 保持消息通道开启以支持异步响应
  return true;
});

// 保存标注数据
async function saveMark(url, markData) {
  const pageKey = normalizePageUrl(url);
  const storage = await chrome.storage.local.get(STORAGE_KEY);
  const marks = storage[STORAGE_KEY] || {};

  if (!marks[pageKey]) {
    marks[pageKey] = [];
  }

  // 添加唯一ID
  markData.id = Date.now() + Math.random();
  marks[pageKey].push(markData);

  await chrome.storage.local.set({ [STORAGE_KEY]: marks });
  console.log(`已保存标注到页面: ${pageKey}`);
}

// 获取所有标注数据
async function getMarks() {
  const storage = await chrome.storage.local.get(STORAGE_KEY);
  return storage[STORAGE_KEY] || {};
}

// 获取指定URL的标注数据
async function getMarksByUrl(url) {
  const pageKey = normalizePageUrl(url);
  const allMarks = await getMarks();
  return allMarks[pageKey] || [];
}

// 清空所有标注数据
async function clearAllMarks() {
  await chrome.storage.local.set({ [STORAGE_KEY]: {} });
}

// 清空指定URL的标注数据
async function clearMarksByUrl(url) {
  const pageKey = normalizePageUrl(url);
  const storage = await chrome.storage.local.get(STORAGE_KEY);
  const marks = storage[STORAGE_KEY] || {};
  delete marks[pageKey];
  await chrome.storage.local.set({ [STORAGE_KEY]: marks });
}

// 删除指定标注
async function removeMark(url, index) {
  const pageKey = normalizePageUrl(url);
  const storage = await chrome.storage.local.get(STORAGE_KEY);
  const marks = storage[STORAGE_KEY] || {};

  if (marks[pageKey] && marks[pageKey][index]) {
    marks[pageKey].splice(index, 1);
    await chrome.storage.local.set({ [STORAGE_KEY]: marks });
  }
}

// 更新标注描述
async function updateMarkDescription(url, index, description) {
  const pageKey = normalizePageUrl(url);
  const storage = await chrome.storage.local.get(STORAGE_KEY);
  const marks = storage[STORAGE_KEY] || {};

  if (marks[pageKey] && marks[pageKey][index]) {
    marks[pageKey][index].desc = description;
    await chrome.storage.local.set({ [STORAGE_KEY]: marks });
  }
}

// 准备导出数据 - 符合site_profiles格式
async function prepareExportData(currentUrl) {
  const allMarks = await getMarks();
  const pageKey = normalizePageUrl(currentUrl);
  const marks = allMarks[pageKey] || [];

  // 生成页面ID - 基于URL路径
  const urlObj = new URL(currentUrl);
  const pageId = urlObj.pathname.replace(/[^a-zA-Z0-9]/g, '_') || 'home';
  const pageName = generatePageName(currentUrl);

  // 生成版本号 - 格式：YYYYMMDDTHHMMSSZ
  const now = new Date();
  const version = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, 'Z');

  // 构建aliases对象 - 符合site_profiles格式
  const aliases = {};
  marks.forEach((mark, index) => {
    const aliasName = `element_${index + 1}`;
    aliases[aliasName] = {
      "selector": mark.candidates?.[0] || mark.cssPath || "",
      "description": mark.desc || `标注元素 ${index + 1}`,
      "role": getElementRole(mark.fingerprint),
      "confidence": 0.8 // 默认置信度
    };
  });

  // 构建site_profiles格式的页面对象
  const pageData = {
    "id": pageId,
    "name": pageName,
    "url_pattern": urlObj.pathname,
    "version": version,
    "generated_at": version,
    "generated_by": "chrome_extension_manual",
    "aliases": aliases
  };

  // 构建完整的site profile格式
  const siteProfile = {
    "version": version,
    "pages": [pageData]
  };

  return siteProfile;
}

// 生成页面名称
function generatePageName(url) {
  try {
    const urlObj = new URL(url);
    const domain = urlObj.hostname;
    const path = urlObj.pathname;

    // 基于路径生成页面名称
    if (path === '/' || path === '') {
      return `${domain}-首页`;
    } else {
      const pathParts = path.split('/').filter(part => part);
      const pageType = pathParts[pathParts.length - 1] || 'page';
      return `${domain}-${pageType}`;
    }
  } catch (error) {
    return "未知页面";
  }
}

// 根据元素指纹推断角色
function getElementRole(fingerprint) {
  if (!fingerprint) return "未知";

  const tag = fingerprint.tag?.toLowerCase();
  const inputType = fingerprint.type?.toLowerCase();

  // 根据HTML标签推断角色
  switch (tag) {
    case 'button':
      return '按钮';
    case 'input':
      return inputType === 'submit' ? '提交按钮' :
             inputType === 'text' ? '文本输入框' :
             inputType === 'password' ? '密码输入框' :
             inputType === 'checkbox' ? '复选框' :
             inputType === 'radio' ? '单选框' : '输入框';
    case 'a':
      return '链接';
    case 'select':
      return '下拉选择框';
    case 'textarea':
      return '多行文本框';
    case 'img':
      return '图片';
    case 'div':
    case 'span':
      return fingerprint.text ? '文本' : '容器';
    case 'ul':
    case 'ol':
      return '列表';
    case 'li':
      return '列表项';
    case 'table':
      return '表格';
    case 'tr':
      return '表格行';
    case 'td':
    case 'th':
      return '表格单元格';
    case 'nav':
      return '导航栏';
    case 'header':
      return '页头';
    case 'footer':
      return '页脚';
    case 'section':
      return '区块';
    case 'article':
      return '文章';
    case 'aside':
      return '侧边栏';
    default:
      return '元素';
  }
}

// 从URL中提取域名
function extractDomain(url) {
  try {
    return new URL(url).host;
  } catch (error) {
    return "unknown";
  }
}

// download_export 消息处理已合并到主消息监听器中

// 处理侧边面板连接
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "sidepanel") {
    console.log('侧边面板已连接');

    port.onDisconnect.addListener(() => {
      console.log('侧边面板已断开连接');
    });
  }
});

// 处理扩展图标点击事件
chrome.action.onClicked.addListener(async (tab) => {
  try {
    console.log('标定工具图标被点击');
    // Chrome Side Panel 会在用户点击图标时自动显示
    // 这里可以添加其他初始化逻辑
  } catch (error) {
    console.error('处理点击事件失败:', error);
  }
});

// 监听标签页更新 - 简化版本，让侧边面板处理注入
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    try {
      // 只记录日志，让侧边面板处理实际的content script注入
      if (tab.url.startsWith('http://') || tab.url.startsWith('https://')) {
        console.log(`标签页 ${tabId} 已完成加载: ${new URL(tab.url).hostname}`);
      }
    } catch (error) {
      console.warn('处理标签页更新时出错:', error);
    }
  }
});

// 扩展安装时的初始化
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('标定工具已安装');
    // 初始化存储
    chrome.storage.local.set({ [STORAGE_KEY]: {} });
  } else if (details.reason === 'update') {
    console.log('标定工具已更新');
  }
});