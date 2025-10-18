// Popup界面脚本
document.addEventListener('DOMContentLoaded', function() {
  const toggleBtn = document.getElementById('toggleBtn');
  const sidePanelBtn = document.getElementById('sidePanelBtn');
  const exportBtn = document.getElementById('exportBtn');
  const status = document.getElementById('status');

  let isPicking = false;

  // 获取当前标签页
  async function getCurrentTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  // 切换标注模式
  toggleBtn.addEventListener('click', async () => {
    try {
      const tab = await getCurrentTab();
      if (!tab) {
        status.textContent = '无法获取当前页面';
        return;
      }

      isPicking = !isPicking;

      // 发送消息到content script
      await chrome.tabs.sendMessage(tab.id, {
        type: 'toggle_picking_mode',
        on: isPicking
      });

      toggleBtn.textContent = isPicking ? '关闭标注模式' : '开启标注模式';
      status.textContent = isPicking ? '标注模式已开启' : '标注模式已关闭';
    } catch (error) {
      console.error('切换标注模式失败:', error);
      status.textContent = '操作失败，请刷新页面重试';
    }
  });

  // 打开侧边面板
  sidePanelBtn.addEventListener('click', async () => {
    try {
      const tab = await getCurrentTab();
      if (!tab) {
        status.textContent = '无法获取当前页面';
        return;
      }

      // 尝试通过不同的方式打开侧边面板
      await chrome.sidePanel.open({ tabId: tab.id }).catch(() => {
        // 如果API不可用，提供手动打开的提示
        status.textContent = '请手动打开侧边面板';
      });
    } catch (error) {
      console.error('打开侧边面板失败:', error);
      status.textContent = '侧边面板功能不可用';
    }
  });

  // 导出数据
  exportBtn.addEventListener('click', async () => {
    try {
      const response = await chrome.runtime.sendMessage({ type: "get_marks" });
      if (response?.ok && Object.keys(response.data).length > 0) {
        await chrome.runtime.sendMessage({
          type: "download_export",
          currentUrl: (await getCurrentTab())?.url || ""
        });
        status.textContent = '导出成功';
      } else {
        status.textContent = '暂无标注数据';
      }
    } catch (error) {
      console.error('导出失败:', error);
      status.textContent = '导出失败';
    }
  });

  // 检查当前状态
  async function checkStatus() {
    try {
      const tab = await getCurrentTab();
      if (!tab) return;

      // 尝试获取页面信息
      const response = await chrome.tabs.sendMessage(tab.id, {
        type: 'get_page_info'
      }).catch(() => null);

      if (response?.ok) {
        status.textContent = '页面已就绪';
      } else {
        status.textContent = '请刷新页面后重试';
      }
    } catch (error) {
      status.textContent = '请刷新页面后重试';
    }
  }

  // 初始化检查
  checkStatus();
});