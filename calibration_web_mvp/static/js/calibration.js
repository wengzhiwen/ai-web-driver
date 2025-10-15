/**
 * 标定工具前端 JavaScript 逻辑。
 */

class CalibrationApp {
    constructor() {
        this.currentSession = null;
        this.currentSnapshot = null;
        this.calibrationElements = [];
        this.selectedNode = null;
        this.domSyncTimestamp = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupEventListeners();
    }

    bindEvents() {
        // 页面加载表单
        document.getElementById('loadPageForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.createSession();
        });

        // 清理缓存按钮
        document.getElementById('clearCacheBtn').addEventListener('click', () => {
            this.clearCache();
        });

        // 调试信息按钮
        document.getElementById('debugInfoBtn').addEventListener('click', () => {
            this.showDebugInfo();
        });

        // 添加元素按钮
        document.getElementById('addElementBtn').addEventListener('click', () => {
            this.addCalibrationElement();
        });

        // 保存 Profile 按钮
        document.getElementById('saveProfileBtn').addEventListener('click', () => {
            this.saveSiteProfile();
        });

  
        // 定位策略选择
        document.querySelectorAll('input[name="locatorStrategy"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.updateSelector();
            });
        });

        // DOM 搜索
        document.getElementById('domSearchInput').addEventListener('input', (e) => {
            this.filterDomTree(e.target.value);
        });

        // A11y 搜索
        document.getElementById('a11ySearchInput').addEventListener('input', (e) => {
            this.filterA11yTree(e.target.value);
        });

        // URL 输入框回车键处理
        document.getElementById('urlInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.createSession();
            }
        });

        // 同步 DOM 按钮
        document.getElementById('syncDomBtn')?.addEventListener('click', () => {
            this.syncDomTree();
        });

        // 关闭会话按钮
        document.getElementById('closeSessionBtn')?.addEventListener('click', () => {
            this.closeSession();
        });
    }

    setupEventListeners() {
        // iframe 高亮通信
        window.addEventListener('message', (event) => {
            // 处理来自 iframe 的高亮完成消息
            if (event.data && event.data.type === 'highlight-complete') {
                console.log('高亮完成:', event.data.domId);
            }
        });

        // 监听 iframe 加载完成
        const pageFrame = document.getElementById('pageFrame');
        pageFrame.addEventListener('load', () => {
            console.log('页面框架加载完成');
        });
    }

    async createSession() {
        const url = document.getElementById('urlInput').value.trim();
        const viewport = {
            width: parseInt(document.getElementById('viewportWidth')?.value || 1280),
            height: parseInt(document.getElementById('viewportHeight')?.value || 720)
        };

        if (!url) {
            this.showError('请输入有效的 URL');
            return;
        }

        this.showLoading(true);
        this.hideMainContent();

        try {
            const response = await fetch('/api/calibrations/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    viewport: viewport
                })
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error?.message || '会话创建失败');
            }

            this.currentSession = data.data;
            this.displaySession();

            // 自动同步 DOM 树
            await this.syncDomTree();

        } catch (error) {
            console.error('会话创建失败:', error);
            this.showError(`会话创建失败: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }

    displaySession() {
        if (!this.currentSession) return;

        // 显示主要内容区域
        this.showMainContent();

        // 更新会话信息显示
        const sessionInfo = document.getElementById('sessionInfo') || document.getElementById('snapshotInfo');
        if (sessionInfo) {
            sessionInfo.textContent = `会话: ${this.currentSession.url.substring(0, 50)}${this.currentSession.url.length > 50 ? '...' : ''}`;
        }

        // 更新按钮状态
        const syncBtn = document.getElementById('syncDomBtn');
        const closeBtn = document.getElementById('closeSessionBtn');
        if (syncBtn) syncBtn.disabled = false;
        if (closeBtn) closeBtn.disabled = false;

        // 清空之前的标定数据
        this.clearCalibrationList();
        this.currentSnapshot = null;

        this.showSuccess('浏览器会话已创建，请在打开的浏览器窗口中进行操作');
    }

    async syncDomTree() {
        if (!this.currentSession) {
            this.showError('没有活跃的会话');
            return;
        }

        try {
            this.showLoading(true, '正在同步 DOM 树...');

            const response = await fetch(`/api/calibrations/sessions/${this.currentSession.session_id}/dom-sync`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    max_depth: 8,
                    max_nodes: 1000,
                    include_bounding_box: true,
                    include_accessibility: true
                })
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error?.message || 'DOM 同步失败');
            }

            this.currentSnapshot = data.data;
            this.domSyncTimestamp = new Date();
            this.displaySnapshot();

        } catch (error) {
            console.error('DOM 同步失败:', error);
            this.showError(`DOM 同步失败: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }

    async closeSession() {
        if (!this.currentSession) {
            return;
        }

        try {
            const response = await fetch(`/api/calibrations/sessions/${this.currentSession.session_id}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showSuccess('会话已关闭');
            }

        } catch (error) {
            console.error('关闭会话失败:', error);
        } finally {
            this.currentSession = null;
            this.currentSnapshot = null;
            this.hideMainContent();
            this.clearCalibrationList();

            // 更新按钮状态
            const syncBtn = document.getElementById('syncDomBtn');
            const closeBtn = document.getElementById('closeSessionBtn');
            if (syncBtn) syncBtn.disabled = true;
            if (closeBtn) closeBtn.disabled = true;
        }
    }

    displaySnapshot() {
        if (!this.currentSnapshot) return;

        // 显示主要内容区域
        this.showMainContent();

        // 更新信息显示
        const infoElement = document.getElementById('snapshotInfo') || document.getElementById('sessionInfo');
        if (infoElement) {
            const nodeCount = this.currentSnapshot.stats?.node_count || 0;
            const timestamp = this.domSyncTimestamp ? this.domSyncTimestamp.toLocaleTimeString() : '';
            const sessionUrl = this.currentSession?.url.substring(0, 30) || '';

            let infoText = '';
            if (this.currentSession) {
                infoText = `会话: ${sessionUrl}${sessionUrl.length >= 30 ? '...' : ''} | ${nodeCount} 节点`;
                if (timestamp) {
                    infoText += ` | 同步于 ${timestamp}`;
                }
            } else {
                infoText = `${this.currentSnapshot.title || '页面'} (${nodeCount} 节点)`;
            }

            infoElement.textContent = infoText;
        }

        // 如果是会话模式，不需要加载 iframe
        if (this.currentSession) {
            // 隐藏页面预览区域或显示提示
            const pagePreview = document.querySelector('.page-preview-container');
            if (pagePreview) {
                pagePreview.innerHTML = `
                    <div class="session-info-placeholder">
                        <i class="bi bi-window-stack display-4 text-muted"></i>
                        <h5 class="mt-3">浏览器会话模式</h5>
                        <p class="text-muted">页面已在独立浏览器窗口中打开</p>
                        <p class="small text-muted">请在浏览器窗口中进行操作，然后点击"同步 DOM 树"按钮</p>
                        <div class="mt-3">
                            <button class="btn btn-primary btn-sm" onclick="app.syncDomTree()">
                                <i class="bi bi-arrow-clockwise"></i> 同步 DOM 树
                            </button>
                        </div>
                    </div>
                `;
            }
        } else {
            // 兼容旧的快照模式
            this.loadPageToIframe();
        }

        // 渲染 DOM 树
        this.renderDomTree();

        // 渲染 A11y 树
        this.renderA11yTree();

        // 清空标定列表
        this.clearCalibrationList();
    }

    async loadPageToIframe() {
        if (!this.currentSnapshot) return;

        try {
            const response = await fetch(`/api/calibrations/snapshots/${this.currentSnapshot.snapshot_id}/html`);
            const htmlContent = await response.text();

            const pageFrame = document.getElementById('pageFrame');
            pageFrame.srcdoc = htmlContent;

        } catch (error) {
            console.error('加载页面 HTML 失败:', error);
            this.showError('加载页面内容失败');
        }
    }

    renderDomTree() {
        const domTree = this.currentSnapshot.dom_tree;
        const container = document.getElementById('domTree');
        container.innerHTML = '';

        if (!domTree || Object.keys(domTree).length === 0) {
            container.innerHTML = '<div class="text-muted">无 DOM 节点</div>';
            return;
        }

        const treeElement = this.createDomTreeNode(domTree, 0);
        container.appendChild(treeElement);
    }

    createDomTreeNode(node, depth) {
        const nodeElement = document.createElement('div');
        nodeElement.className = 'dom-node';
        nodeElement.style.paddingLeft = `${depth * 20}px`;

        const nodeContent = document.createElement('div');
        nodeContent.className = 'dom-node-content';
        nodeContent.dataset.domId = node.dom_id;

        // 节点标签和属性
        let label = `<span class="tag">${node.tag}</span>`;

        if (node.attrs) {
            if (node.attrs.id) {
                label += ` <span class="attr-id">#${node.attrs.id}</span>`;
            }
            if (node.attrs.class) {
                const classes = node.attrs.class.split(' ').slice(0, 2).join('.');
                label += ` <span class="attr-class">.${classes}</span>`;
            }
            if (node.attrs.role) {
                label += ` <span class="attr-role">[${node.attrs.role}]</span>`;
            }
            if (node.attrs['data-test']) {
                label += ` <span class="attr-data-test">data-test="${node.attrs['data-test']}"</span>`;
            }
        }

        if (node.text) {
            label += ` <span class="text">"${node.text}"</span>`;
        }

        nodeContent.innerHTML = label;

        // 点击事件
        nodeContent.addEventListener('click', () => {
            this.selectNode(node);
        });

        nodeElement.appendChild(nodeContent);

        // 子节点
        if (node.children && node.children.length > 0) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'dom-children';

            node.children.forEach(child => {
                const childElement = this.createDomTreeNode(child, depth + 1);
                childrenContainer.appendChild(childElement);
            });

            nodeElement.appendChild(childrenContainer);
        }

        return nodeElement;
    }

    renderA11yTree() {
        const a11yTree = this.currentSnapshot.a11y_tree;
        const container = document.getElementById('a11yTree');
        container.innerHTML = '';

        if (!a11yTree || Object.keys(a11yTree).length === 0) {
            container.innerHTML = '<div class="text-muted">无可访问性节点</div>';
            return;
        }

        const treeElement = this.createA11yTreeNode(a11yTree, 0);
        container.appendChild(treeElement);
    }

    createA11yTreeNode(node, depth) {
        const nodeElement = document.createElement('div');
        nodeElement.className = 'a11y-node';
        nodeElement.style.paddingLeft = `${depth * 20}px`;

        const nodeContent = document.createElement('div');
        nodeContent.className = 'a11y-node-content';

        let label = '';
        if (node.role) {
            label += `<span class="role">${node.role}</span>`;
        }
        if (node.name) {
            label += ` <span class="name">"${node.name}"</span>`;
        }
        if (node.value) {
            label += ` <span class="value">= "${node.value}"</span>`;
        }

        nodeContent.innerHTML = label || '<span class="text-muted">无角色信息</span>';

        // 点击事件 - 尝试找到对应的 DOM 节点
        nodeContent.addEventListener('click', () => {
            this.findAndSelectDomNodeByA11y(node);
        });

        nodeElement.appendChild(nodeContent);

        // 子节点
        if (node.children && node.children.length > 0) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'a11y-children';

            node.children.forEach(child => {
                const childElement = this.createA11yTreeNode(child, depth + 1);
                childrenContainer.appendChild(childElement);
            });

            nodeElement.appendChild(childrenContainer);
        }

        return nodeElement;
    }

    selectNode(node) {
        this.selectedNode = node;

        // 更新选中状态
        document.querySelectorAll('.dom-node-content, .a11y-node-content').forEach(el => {
            el.classList.remove('selected');
        });

        const selectedElement = document.querySelector(`[data-dom-id="${node.dom_id}"]`);
        if (selectedElement) {
            selectedElement.classList.add('selected');
        }

        // 高亮页面中的元素
        this.highlightElement(node.dom_id);

        // 显示节点信息模态框
        this.showNodeModal(node);
    }

    async highlightElement(domId) {
        if (!domId) return;

        if (this.currentSession) {
            // 会话模式：通过 API 高亮
            try {
                const response = await fetch(`/api/calibrations/sessions/${this.currentSession.session_id}/highlight`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        dom_id: domId,
                        action: 'show'
                    })
                });

                const data = await response.json();

                if (!data.success) {
                    console.warn('高亮失败:', data.error?.message);
                }
            } catch (error) {
                console.error('高亮请求失败:', error);
            }
        } else {
            // 快照模式：通过 iframe 高亮
            const pageFrame = document.getElementById('pageFrame');
            if (pageFrame && pageFrame.contentWindow) {
                pageFrame.contentWindow.postMessage({
                    type: 'highlight',
                    domId: domId
                }, '*');
            }
        }
    }

    async clearHighlight() {
        if (this.currentSession) {
            // 会话模式：通过 API 清除高亮
            try {
                await fetch(`/api/calibrations/sessions/${this.currentSession.session_id}/highlight`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'hide'
                    })
                });
            } catch (error) {
                console.error('清除高亮请求失败:', error);
            }
        } else {
            // 快照模式：通过 iframe 清除高亮
            const pageFrame = document.getElementById('pageFrame');
            if (pageFrame && pageFrame.contentWindow) {
                pageFrame.contentWindow.postMessage({
                    type: 'clear-highlight'
                }, '*');
            }
        }
    }

    showNodeModal(node) {
        // 填充节点基本信息
        document.getElementById('nodeTag').value = node.tag || '';
        document.getElementById('nodeDomId').value = node.dom_id || '';
        document.getElementById('nodeClass').value = node.attrs?.class || '';
        document.getElementById('nodeRole').value = node.attrs?.role || '';
        document.getElementById('nodeText').value = node.text || '';
        document.getElementById('nodePath').value = node.path || '';

        // 生成默认别名
        const defaultAlias = this.generateDefaultAlias(node);
        document.getElementById('elementAlias').value = defaultAlias;

        // 生成默认描述
        const defaultDescription = this.generateDefaultDescription(node);
        document.getElementById('elementDescription').value = defaultDescription;

        // 设置默认选择器
        this.updateSelector();

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('nodeModal'));
        modal.show();
    }

    generateDefaultAlias(node) {
        const tag = node.tag || '';
        const role = node.attrs?.role || '';
        const id = node.attrs?.id || '';
        const dataTest = node.attrs?.['data-test'] || '';

        if (dataTest) {
            return dataTest.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
        }

        if (id) {
            return id.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
        }

        let alias = tag;
        if (role) {
            alias += `_${role}`;
        }

        return alias.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
    }

    generateDefaultDescription(node) {
        const tag = node.tag || '';
        const role = node.attrs?.role || '';
        const text = node.text || '';
        const placeholder = node.attrs?.placeholder || '';
        const ariaLabel = node.attrs?.['aria-label'] || '';

        let description = '';

        if (text && text.length <= 50) {
            description = text;
        } else if (placeholder) {
            description = `${tag}输入框，${placeholder}`;
        } else if (ariaLabel) {
            description = `${tag}，${ariaLabel}`;
        } else if (role) {
            description = `${role}`;
        } else {
            description = tag;
        }

        return description;
    }

    updateSelector() {
        if (!this.selectedNode) return;

        const strategy = document.querySelector('input[name="locatorStrategy"]:checked').value;
        let selector = '';

        switch (strategy) {
            case 'dom_path':
                selector = this.selectedNode.path || '';
                break;
            case 'data_test':
                if (this.selectedNode.attrs?.['data-test']) {
                    selector = `[data-test="${this.selectedNode.attrs['data-test']}"]`;
                }
                break;
            case 'id_class':
                if (this.selectedNode.attrs?.id) {
                    selector = `#${this.selectedNode.attrs.id}`;
                } else if (this.selectedNode.attrs?.class) {
                    const firstClass = this.selectedNode.attrs.class.split(' ')[0];
                    selector = `${this.selectedNode.tag}.${firstClass}`;
                } else {
                    selector = this.selectedNode.path || '';
                }
                break;
        }

        document.getElementById('elementSelector').value = selector;
    }

    addCalibrationElement() {
        if (!this.selectedNode) return;

        const alias = document.getElementById('elementAlias').value.trim();
        const description = document.getElementById('elementDescription').value.trim();
        const selector = document.getElementById('elementSelector').value.trim();
        const strategy = document.querySelector('input[name="locatorStrategy"]:checked').value;

        if (!alias) {
            this.showError('请输入别名');
            return;
        }

        if (!selector) {
            this.showError('请输入选择器');
            return;
        }

        // 检查别名是否已存在
        if (this.calibrationElements.some(el => el.alias === alias)) {
            this.showError('别名已存在');
            return;
        }

        const element = {
            alias: alias,
            selector: selector,
            description: description,
            role: this.selectedNode.attrs?.role || '',
            locator_strategy: strategy,
            dom_id: this.selectedNode.dom_id,
            bounding_box: null, // 可以后续添加
            a11y: {
                role: this.selectedNode.attrs?.role || '',
                name: this.selectedNode.text || '',
            }
        };

        this.calibrationElements.push(element);
        this.updateCalibrationList();

        // 关闭模态框
        const modal = bootstrap.Modal.getInstance(document.getElementById('nodeModal'));
        modal.hide();

        // 清除高亮
        this.clearHighlight();

        this.showSuccess(`已添加元素: ${alias}`);
    }

    updateCalibrationList() {
        const container = document.getElementById('calibrationList');
        const countBadge = document.getElementById('elementCount');

        countBadge.textContent = this.calibrationElements.length;

        if (this.calibrationElements.length === 0) {
            container.innerHTML = `
                <div class="text-muted text-center py-4">
                    <i class="bi bi-inbox display-4"></i>
                    <p class="mt-2">暂无标定元素</p>
                </div>
            `;
            return;
        }

        container.innerHTML = '';

        this.calibrationElements.forEach((element, index) => {
            const elementCard = document.createElement('div');
            elementCard.className = 'calibration-element-card';
            elementCard.innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <h6 class="card-title">${element.alias}</h6>
                                <p class="card-text small text-muted">${element.description || '无描述'}</p>
                                <div class="small">
                                    <span class="badge bg-secondary">${element.locator_strategy}</span>
                                    <code class="ms-2">${element.selector}</code>
                                </div>
                            </div>
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-primary" onclick="app.highlightElement('${element.dom_id}')">
                                    <i class="bi bi-eye"></i>
                                </button>
                                <button class="btn btn-outline-danger" onclick="app.removeCalibrationElement(${index})">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            container.appendChild(elementCard);
        });
    }

    removeCalibrationElement(index) {
        this.calibrationElements.splice(index, 1);
        this.updateCalibrationList();
        this.showSuccess('元素已删除');
    }

    clearCalibrationList() {
        this.calibrationElements = [];
        this.updateCalibrationList();
    }

    async saveSiteProfile() {
        if (!this.currentSnapshot) {
            this.showError('没有可用的页面数据');
            return;
        }

        if (this.calibrationElements.length === 0) {
            this.showError('没有标定元素');
            return;
        }

        const siteName = document.getElementById('siteName').value.trim();
        const siteBaseUrl = document.getElementById('siteBaseUrl').value.trim();
        const pageId = document.getElementById('pageId').value.trim();
        const urlPattern = document.getElementById('urlPattern').value.trim();
        const pageSummary = document.getElementById('pageSummary').value.trim();
        const pageNotes = document.getElementById('pageNotes').value.trim();

        if (!siteName) {
            this.showError('请输入站点名称');
            return;
        }

        if (!pageId) {
            this.showError('请输入页面 ID');
            return;
        }

        const profileData = {
            site: {
                name: siteName,
                base_url: siteBaseUrl || (this.currentSession ? this.currentSession.url : this.currentSnapshot.url)
            },
            page: {
                page_id: pageId,
                url_pattern: urlPattern || (this.currentSession ? this.currentSession.url : this.currentSnapshot.url),
                summary: pageSummary,
                notes: pageNotes
            },
            elements: this.calibrationElements
        };

        // 如果是会话模式，添加会话相关信息
        if (this.currentSession) {
            profileData.session_id = this.currentSession.session_id;

            // 可选：持久化快照
            try {
                const persistResponse = await fetch(`/api/calibrations/sessions/${this.currentSession.session_id}/persist-snapshot`, {
                    method: 'POST'
                });

                const persistData = await persistResponse.json();
                if (persistData.success) {
                    profileData.snapshot_token = persistData.data.snapshot_token;
                }
            } catch (error) {
                console.warn('快照持久化失败，继续保存 Profile:', error);
            }
        } else {
            // 快照模式
            profileData.snapshot_id = this.currentSnapshot.snapshot_id;
        }

        try {
            const response = await fetch('/api/calibrations/site-profiles', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(profileData)
            });

            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error?.message || '保存失败');
            }

            // 关闭模态框
            const modal = bootstrap.Modal.getInstance(document.getElementById('saveProfileModal'));
            modal.hide();

            this.showSuccess(`Site Profile 已保存: ${data.data.filename}`);

            // 清空表单
            document.getElementById('saveProfileForm').reset();

        } catch (error) {
            console.error('保存 Site Profile 失败:', error);
            this.showError(`保存失败: ${error.message}`);
        }
    }

    async clearCache() {
        try {
            const response = await fetch('/cleanup', {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.showSuccess(`已清理 ${data.cleaned_count} 个旧快照`);
            } else {
                throw new Error(data.error || '清理失败');
            }
        } catch (error) {
            console.error('清理缓存失败:', error);
            this.showError(`清理失败: ${error.message}`);
        }
    }

    async showDebugInfo() {
        try {
            const response = await fetch('/api/calibrations/debug/stats');
            const data = await response.json();

            if (data.success) {
                const stats = data.data;
                const debugContent = document.getElementById('debugContent');
                debugContent.innerHTML = `
                    <div class="row">
                        <div class="col-md-6">
                            <h6>快照统计</h6>
                            <table class="table table-sm">
                                <tr>
                                    <td>快照数量</td>
                                    <td>${stats.snapshot_count}</td>
                                </tr>
                                <tr>
                                    <td>总大小</td>
                                    <td>${stats.total_size_mb} MB</td>
                                </tr>
                                <tr>
                                    <td>最早快照</td>
                                    <td>${stats.oldest_snapshot || '无'}</td>
                                </tr>
                                <tr>
                                    <td>最新快照</td>
                                    <td>${stats.newest_snapshot || '无'}</td>
                                </tr>
                            </table>
                        </div>
                        <div class="col-md-6">
                            <h6>当前快照</h6>
                            <table class="table table-sm">
                                <tr>
                                    <td>快照 ID</td>
                                    <td>${this.currentSnapshot?.snapshot_id || '无'}</td>
                                </tr>
                                <tr>
                                    <td>节点数量</td>
                                    <td>${this.currentSnapshot?.stats?.node_count || 0}</td>
                                </tr>
                                <tr>
                                    <td>最大深度</td>
                                    <td>${this.currentSnapshot?.stats?.max_depth || 0}</td>
                                </tr>
                                <tr>
                                    <td>标定元素</td>
                                    <td>${this.calibrationElements.length}</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                `;

                const modal = new bootstrap.Modal(document.getElementById('debugModal'));
                modal.show();
            } else {
                throw new Error(data.error?.message || '获取调试信息失败');
            }
        } catch (error) {
            console.error('获取调试信息失败:', error);
            this.showError(`获取调试信息失败: ${error.message}`);
        }
    }

    filterDomTree(searchTerm) {
        const allNodes = document.querySelectorAll('.dom-node');
        const term = searchTerm.toLowerCase().trim();

        allNodes.forEach(node => {
            const content = node.textContent.toLowerCase();
            if (term === '' || content.includes(term)) {
                node.style.display = '';
            } else {
                node.style.display = 'none';
            }
        });
    }

    filterA11yTree(searchTerm) {
        const allNodes = document.querySelectorAll('.a11y-node');
        const term = searchTerm.toLowerCase().trim();

        allNodes.forEach(node => {
            const content = node.textContent.toLowerCase();
            if (term === '' || content.includes(term)) {
                node.style.display = '';
            } else {
                node.style.display = 'none';
            }
        });
    }

    findAndSelectDomNodeByA11y(a11yNode) {
        // 尝试通过 name、role 等属性找到对应的 DOM 节点
        if (!this.currentSnapshot) return;

        const domTree = this.currentSnapshot.dom_tree;
        const foundNode = this.searchDomTreeByA11y(domTree, a11yNode);

        if (foundNode) {
            this.selectNode(foundNode);
        } else {
            this.showError('未找到对应的 DOM 节点');
        }
    }

    searchDomTreeByA11y(domNode, a11yNode) {
        if (!domNode) return null;

        // 简单的匹配逻辑
        if (domNode.text && a11yNode.name &&
            domNode.text.toLowerCase().includes(a11yNode.name.toLowerCase())) {
            return domNode;
        }

        if (domNode.attrs?.role && a11yNode.role &&
            domNode.attrs.role.toLowerCase() === a11yNode.role.toLowerCase()) {
            return domNode;
        }

        // 递归搜索子节点
        if (domNode.children) {
            for (const child of domNode.children) {
                const found = this.searchDomTreeByA11y(child, a11yNode);
                if (found) return found;
            }
        }

        return null;
    }

    showLoading(show, message = '正在加载...') {
        const loadingStatus = document.getElementById('loadingStatus');
        const loadBtn = document.getElementById('loadPageBtn');
        const loadingText = loadingStatus?.querySelector('span:last-child');

        if (show) {
            if (loadingStatus) {
                loadingStatus.style.display = 'block';
                if (loadingText) {
                    loadingText.textContent = message;
                }
            }
            if (loadBtn) loadBtn.disabled = true;
        } else {
            if (loadingStatus) {
                loadingStatus.style.display = 'none';
            }
            if (loadBtn) loadBtn.disabled = false;
        }
    }

    showMainContent() {
        document.getElementById('mainContent').style.display = 'block';
    }

    hideMainContent() {
        document.getElementById('mainContent').style.display = 'none';
    }

    showError(message) {
        const errorToast = document.getElementById('errorToast');
        const errorMessage = document.getElementById('errorMessage');

        errorMessage.textContent = message;
        const toast = new bootstrap.Toast(errorToast);
        toast.show();
    }

    showSuccess(message) {
        const successToast = document.getElementById('successToast');
        const successMessage = document.getElementById('successMessage');

        successMessage.textContent = message;
        const toast = new bootstrap.Toast(successToast);
        toast.show();
    }
}

// 初始化应用
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new CalibrationApp();
});