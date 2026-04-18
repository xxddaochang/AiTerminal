// UMD 导入
const { createApp, ref, onMounted, onUnmounted, nextTick, watch, computed } = window.Vue;
const Terminal = window.Terminal;
const FitAddon = window.FitAddon.FitAddon;

const THEME_PRESETS = {
    dark: {
        background: '#1e1e1e',
        foreground: '#ffffff',
        selectionBackground: 'rgba(255, 255, 255, 0.3)'
    },
    light: {
        background: '#ffffff',
        foreground: '#000000',
        selectionBackground: 'rgba(0, 0, 0, 0.3)',
        cursor: '#000000'
    },
    dracula: {
        background: '#282a36',
        foreground: '#f8f8f2',
        selectionBackground: '#44475a',
        cursor: '#f8f8f2'
    },
    cyberpunk: {
        background: '#0d0221',
        foreground: '#00ff41',
        selectionBackground: '#ff003c',
        cursor: '#00ff41'
    },
    vscode: {
        background: '#1e1e1e',
        foreground: '#d4d4d4',
        selectionBackground: '#264f78',
        cursor: '#ffffff',
        cursorAccent: '#000000'
    }
};

// Highlight.js 主题映射
const HLJS_THEME_MAP = {
    dark: 'atom-one-dark',
    light: 'github',
    dracula: 'dracula',
    cyberpunk: 'monokai',
    vscode: 'vs2015'
};

// 动态切换 Highlight.js 主题
const switchHljsTheme = (theme) => {
    const hljsTheme = HLJS_THEME_MAP[theme] || 'atom-one-dark';
    const link = document.getElementById('hljs-theme');
    if (link) {
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${hljsTheme}.min.css`;
    }
};

// 主题预览渐变色生成
const getThemePreviewGradient = (themeName) => {
    const gradients = {
        dark: '#1e1e1e, #2d2d2d',
        light: '#ffffff, #f0f0f0',
        dracula: '#282a36, #44475a',
        cyberpunk: '#0d0221, #ff003c',
        vscode: '#1e1e1e, #264f78',
        monokai: '#272822, #49483e',
        nord: '#2e3440, #4c566a',
        solarized: '#002b36, #073642'
    };
    return gradients[themeName] || '#1e1e1e, #2d2d2d';
};

const FileTree = {
    name: 'FileTree',
    props: { items: Array },
    template: `
        <ul class="pl-2 space-y-1">
            <li v-for="item in items" :key="item.path">
                <div @click.stop="toggle(item)" 
                     :class="[
                        item.type === 'dir' ? 'cursor-pointer' : 'cursor-default',
                        'rounded px-2 py-1 flex items-center gap-2 text-sm text-gray-300 transition-colors duration-150 hover:bg-gray-800 group'
                     ]">
                    <span v-if="item.type === 'dir'" class="opacity-70 group-hover:opacity-100 transition-opacity">{{ item.isOpen ? '📂' : '📁' }}</span>
                    <span v-else class="opacity-70 group-hover:opacity-100 transition-opacity">📄</span>
                    <span class="truncate">{{ item.name }}</span>
                </div>
                <file-tree 
                    v-if="item.type === 'dir' && item.isOpen" 
                    :items="item.children" 
                    @open="$emit('open', $event)"
                    @open-dir="$emit('open-dir', $event)"
                ></file-tree>
            </li>
        </ul>
    `,
    setup(props, { emit }) {
        const toggle = (item) => {
            if (item.type === 'dir') {
                item.isOpen = !item.isOpen;
                if (item.isOpen && (!item.children || item.children.length === 0)) {
                    emit('open-dir', item);
                }
            }
        };
        return { toggle };
    }
};

const app = createApp({
    components: { FileTree },
    setup() {
        const isChatMode = ref(false);

        // 状态
        const showSidebar = ref(true);
        const showAgent = ref(true);
        const currentModel = ref('deepseek');
        const inputMessage = ref('');
        const showSettings = ref(false);
        const chatContainer = ref(null);
        const isLoading = ref(false);
        const showTimeline = ref(false);
        // Fix: AbortController for Stop Generation
        let abortController = null;
        const showApiKey = ref(false);

        // 规则
        const showRules = ref(false);
        const showThemes = ref(false);
        const rulesList = ref([]);
        const selectedRuleName = ref(null);
        const ruleContent = ref('');
        const activeRule = ref(null);
        const showNewRuleModal = ref(false);
        const newRuleName = ref('');
        const activeSettingsTab = ref('general'); // 设置面板标签页

        // 主题市场
        const showThemeMarket = ref(false);
        const themesList = ref([]);
        const previewTheme = ref(null);
        const isLoadingThemes = ref(false);

        // 提示 & 模态框
        const toasts = ref([]);
        let toastCounter = 0;
        const confirmModal = ref({ visible: false, title: '', message: '', resolve: null });

        // 跨窗口同步广播通道
        const broadcastChannel = new BroadcastChannel('ai-term-sync');

        broadcastChannel.onmessage = async (event) => {
            const { type, data } = event.data;
            // console.log('[Main] Received broadcast:', type, data);

            switch (type) {
                case 'request_history':
                    // Send history AND config for initial sync (Strip Proxies)
                    // Send current history and config to popup
                    // Strip Proxies
                    const historyPayload = JSON.parse(JSON.stringify(chatHistory.value));
                    const configPayload = JSON.parse(JSON.stringify(config.value));
                    broadcastChannel.postMessage({
                        type: 'initChat',
                        chatHistory: historyPayload,
                        config: configPayload
                    });
                    // Sync isLoading state
                    broadcastChannel.postMessage({
                        type: 'loading_state',
                        data: isLoading.value
                    });
                    break;
                case 'new_message':
                    // 修复 2: ID 去重
                    // 检查是否已存在相同 ID 的消息
                    const exists = data.id && chatHistory.value.some(m => m.id === data.id);

                    if (!exists) {
                        // Fallback: 如果没有 ID (旧消息)，使用内容+角色去重 (检查最后3条)
                        const recent = chatHistory.value.slice(-3);
                        const isDupContent = !data.id && recent.some(m => m.role === data.role && m.content === data.content);

                        if (!isDupContent) {
                            chatHistory.value.push(data);
                            scrollToBottom();
                        }
                    }
                    break;
                case 'trigger_chat':
                    // 弹出窗口请求主窗口发送消息到后端
                    if (data.id) {
                        // 使用 Web Locks API 确保只有一个标签页处理此消息
                        navigator.locks.request(`ai_term_msg_${data.id}`, { ifAvailable: true }, async (lock) => {
                            if (!lock) return; // 锁被占用，忽略
                            inputMessage.value = data.content;
                            await sendMessage(data.id);
                        });
                    } else {
                        inputMessage.value = data.content;
                        await sendMessage(data.id); // Should be undefined if not provided, consistent with logic
                    }
                    break;
                case 'execute_command':
                    // Revert document.hidden check as it blocks background tabs (popup active = main hidden)
                    // Use Web Locks to ensure only one main window handles the command
                    const cmdId = data.id || `cmd_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    navigator.locks.request(`ai_term_cmd_${cmdId}`, { ifAvailable: true }, async (lock) => {
                        if (!lock) return;
                        console.log('[Main] Executing command:', data, 'Lock acquired');
                        handleRemoteCommand(data);
                    });
                    break;
                case 'change_model':
                    console.log('[Main] Received switch request:', data);
                    if (config.value && config.value.providers && config.value.providers[data.provider]) {
                        console.log('[Main] Changing model to:', data.provider);
                        config.value.activeProvider = data.provider;
                        handleModelChange();
                    } else {
                        const keys = (config.value && config.value.providers) ? Object.keys(config.value.providers) : [];
                        console.warn('[Main] Invalid provider:', data.provider, 'Available:', keys);
                    }
                    break;
                case 'stop_generation':
                    stopGeneration(false); // Don't ask again if triggered from popup (popup handles confirm)
                    break;
            }
        };

        const handleRemoteCommand = (cmdData) => {
            console.log('[Main] Handling remote command:', cmdData);
            const tab = tabs.value.find(t => t.id === activeTabId.value);

            if (!tab) {
                // If no active tab, try the last one or create one?
                // Or just pick the first available tab
                const firstTab = tabs.value[0];
                if (firstTab) {
                    activeTabId.value = firstTab.id;
                    nextTick(() => handleRemoteCommand(cmdData));
                    return;
                }
                showToast('Error', 'No terminal tabs open', 'error');
                return;
            }

            if (!tab.socket || tab.socket.readyState !== 1) {
                showToast('Error', `Terminal ${tab.id} disconnected`, 'error');
                return;
            }

            // Ensure terminal is focused
            if (tab.term) tab.term.focus();

            switch (cmdData.action) {
                case 'run':
                    // 后端期望终端输入的原始字符串
                    tab.socket.send(cmdData.code + '\n');
                    showToast('Success', 'Command sent from Popup', 'success');
                    break;
                case 'input':
                    // 后端期望终端输入的原始字符串. Prepend space to prevent history pollution and ensures first char isn't eaten?
                    // actually, let's just send it. If char is eaten, maybe focus issue.
                    // Let's try sending it directly first with focus.
                    // tab.socket.send(' ' + cmdData.code); 
                    // User complained about dropping first char.
                    // It's safer to just send it.
                    console.log('[Main] Sending input to terminal:', cmdData.code);
                    tab.socket.send(cmdData.code);
                    showToast('Success', 'Input sent from Popup', 'success');
                    break;
            }
        };

        // 布局
        const sidebarWidth = ref(250);
        const agentWidth = ref(350);
        const isResizing = ref(null);

        // --- 工具函数 ---
        const scrollToBottom = () => {
            nextTick(() => {
                const container = document.querySelector('.chat-messages');
                if (container) container.scrollTop = container.scrollHeight;
            });
        };

        // 选择 & 上下文
        const selectionOverlay = ref({ visible: false, x: 0, y: 0, type: '', text: '' });
        const contextMenu = ref({ visible: false, x: 0, y: 0, text: '' });
        const termContextMap = ref(new Map());
        const tokenCounter = ref(0);
        const contextChips = ref([]);

        // Watch and broadcast context chips
        watch(contextChips, (newChips) => {
            // Strip Proxies
            const payload = JSON.parse(JSON.stringify(newChips));
            broadcastChannel.postMessage({
                type: 'context_update',
                data: payload
            });
        }, { deep: true });

        // 配置
        // Config
        const config = ref({
            activeProvider: 'deepseek',
            providers: {
                deepseek: { apiKey: '', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
                doubao: { apiKey: '', baseUrl: 'https://ark.cn-beijing.volces.com/api/v3', model: '' },
                qwen: { apiKey: '', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' }
            },
            theme: 'dark'
        });

        const currentModelName = computed(() => {
            if (!config.value || !config.value.providers) return '';
            const p = config.value.activeProvider || 'deepseek';
            return config.value.providers[p]?.model || '';
        });

        // 数据
        const chatHistory = ref([{ role: 'ai', content: 'Hello! I am your AI Terminal Assistant.' }]);
        const files = ref([]);
        const tabs = ref([]);
        const activeTabId = ref(null);
        let tabCounter = 0;
        const chatSessions = ref([]);
        const currentSessionId = ref(null);
        const showHistory = ref(false);

        // 聊天持久化
        let saveTimer = null;

        // 加载聊天记录
        const loadChatHistory = async () => {
            try {
                const res = await fetch('/api/chat/load', { headers: getHeaders() });
                const data = await res.json();
                if (data.chatHistory && data.chatHistory.length > 0) {
                    chatHistory.value = data.chatHistory;
                    console.log('Chat history loaded:', data.filepath);
                }
            } catch (error) {
                console.error('Failed to load chat history:', error);
            }
        };

        // 保存聊天记录
        const saveChatHistory = async () => {
            try {
                const res = await fetch('/api/chat/save', {
                    method: 'POST',
                    headers: { ...getHeaders(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chatHistory: chatHistory.value })
                });
                const data = await res.json();
                if (data.success) {
                    console.log('Chat history saved:', data.filepath);
                }
            } catch (error) {
                console.error('Failed to save chat history:', error);
            }
        };


        // --- 辅助函数 ---
        const getHeaders = () => {
            const headers = { 'Content-Type': 'application/json' };
            if (config.value && config.value.access_token) {
                headers['X-Access-Token'] = config.value.access_token;
            }
            return headers;
        };

        const showToast = (title, message, type = 'info') => {
            const id = ++toastCounter;
            toasts.value.push({ id, title, message, type });
            setTimeout(() => removeToast(id), 3000);
        };

        const removeToast = (id) => {
            const index = toasts.value.findIndex(t => t.id === id);
            if (index !== -1) toasts.value.splice(index, 1);
        };

        const requestConfirm = (title, message) => {
            return new Promise((resolve) => {
                confirmModal.value = {
                    visible: true, title, message,
                    resolve: (val) => {
                        confirmModal.value.visible = false;
                        resolve(val);
                    }
                };
            });
        };

        const closeConfirm = (result) => {
            if (confirmModal.value.resolve) confirmModal.value.resolve(result);
        };

        // --- Chips (标签) ---
        const removeChip = (index) => contextChips.value.splice(index, 1);
        const clearChips = () => contextChips.value = [];

        // --- 配置 ---
        const loadConfig = async () => {
            try {
                // 从数据库加载模型配置
                const modelsRes = await fetch('/api/models');
                const modelsData = await modelsRes.json();

                if (modelsData.models && modelsData.models.length > 0) {
                    // 将数据库模型转换为前端格式
                    const providers = {};
                    let activeProvider = 'deepseek';

                    for (const model of modelsData.models) {
                        providers[model.provider_name] = {
                            apiKey: model.api_key || '',
                            baseUrl: model.base_url || '',
                            model: model.default_model || ''
                        };
                    }

                    // 获取激活的模型
                    try {
                        const activeRes = await fetch('/api/models/active/current');
                        const activeModel = await activeRes.json();
                        if (activeModel && activeModel.provider_name) {
                            activeProvider = activeModel.provider_name;
                        }
                    } catch (e) {
                        console.log('No active model found, using default');
                    }

                    config.value.providers = providers;
                    config.value.activeProvider = activeProvider;
                }

                // 加载主题配置
                const configRes = await fetch('/api/agent/config');
                const configData = await configRes.json();
                config.value.theme = configData.theme || 'dark';

                await loadRules();
            } catch (e) {
                console.error('Failed to load config:', e);
                showToast('Error', 'Failed to load config', 'error');
            }
        };

        const saveConfig = async () => {
            try {
                // 保存每个模型配置到数据库
                for (const [providerName, providerConfig] of Object.entries(config.value.providers)) {
                    await fetch(`/api/models/${providerName}`, {
                        method: 'POST',
                        headers: getHeaders(),
                        body: JSON.stringify({
                            api_key: providerConfig.apiKey,
                            base_url: providerConfig.baseUrl,
                            default_model: providerConfig.model,
                            is_active: true
                        })
                    });
                }

                // 激活当前选中的模型
                if (config.value.activeProvider) {
                    await fetch(`/api/models/${config.value.activeProvider}/activate`, {
                        method: 'PUT',
                        headers: getHeaders()
                    });
                }

                // 保存主题配置
                await fetch('/api/agent/config', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ theme: config.value.theme })
                });

                showSettings.value = false;
                showToast('Success', '设置已保存', 'success');
            } catch (e) {
                console.error('Failed to save settings:', e);
                showToast('Error', '保存设置失败', 'error');
            }
        };

        const handleModelChange = async () => {
            const newProvider = config.value.activeProvider;
            if (!newProvider) return;

            try {
                // 调用后端激活接口
                await fetch(`/api/models/${newProvider}/activate`, {
                    method: 'PUT',
                    headers: getHeaders()
                });

                // 显示提示
                const providerName = {
                    'deepseek': 'DeepSeek',
                    'qwen': '通义千问',
                    'doubao': '豆包'
                }[newProvider] || newProvider;

                showToast('Success', `已切换模型为: ${providerName}`, 'success');

                // Broadcast config update (Strip Proxies)
                broadcastChannel.postMessage({
                    type: 'config_update',
                    data: JSON.parse(JSON.stringify({
                        activeProvider: config.value.activeProvider,
                        providers: config.value.providers
                    }))
                });

                // Save to persist
                await saveConfig();
            } catch (e) {
                console.error('Failed to activate model:', e);
                showToast('Error', '切换模型失败', 'error');
            }
        };



        const toggleTheme = async () => {
            const themes = Object.keys(THEME_PRESETS);
            const currentIdx = themes.indexOf(config.value.theme);
            const nextIdx = (currentIdx + 1) % themes.length;
            const nextTheme = themes[nextIdx];

            // 先更新配置
            config.value.theme = nextTheme;

            // 应用主题但不显示提示
            await applyTheme(nextTheme, false);  // 传递 false 以抑制提示

            // Save config and show single toast
            try {
                await fetch('/api/agent/config', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify(config.value)
                });

                // Broadcast theme update
                broadcastChannel.postMessage({
                    type: 'theme_update',
                    data: nextTheme
                });

                showToast('Success', `已应用主题: ${nextTheme}`, 'success');
            } catch (e) {
                showToast('Error', 'Failed to save theme', 'error');
            }
        };

        // --- Theme Market ---
        const loadThemes = async () => {
            isLoadingThemes.value = true;
            try {
                const res = await fetch('/api/themes');
                themesList.value = await res.json();
            } catch (e) {
                showToast('Error', '加载主题列表失败', 'error');
            } finally {
                isLoadingThemes.value = false;
            }
        };

        const applyTheme = async (themeName, showToastNotification = true) => {
            try {
                const res = await fetch(`/api/themes/${themeName}`);
                const themeData = await res.json();

                // 更新配置
                config.value.theme = themeName;

                // 动态更新 THEME_PRESETS
                THEME_PRESETS[themeName] = themeData.terminal;

                // 更新代码高亮主题
                if (themeData.hljs) {
                    HLJS_THEME_MAP[themeName] = themeData.hljs;
                    switchHljsTheme(themeName);
                }

                // 应用到所有终端
                tabs.value.forEach(tab => {
                    if (tab.term) {
                        tab.term.options.theme = themeData.terminal;
                    }
                });

                // 仅在非 toggleTheme 调用时保存配置并显示提示
                if (showToastNotification) {
                    await saveConfig();
                    showToast('Success', `已应用主题: ${themeData.displayName || themeName}`, 'success');
                }
            } catch (e) {
                if (showToastNotification) {
                    showToast('Error', '应用主题失败', 'error');
                }
            }
        };

        const previewThemeAction = async (themeName) => {
            try {
                const res = await fetch(`/api/themes/${themeName}`);
                const themeData = await res.json();
                previewTheme.value = themeData;

                // 临时应用预览
                tabs.value.forEach(tab => {
                    if (tab.term) {
                        tab.term.options.theme = themeData.terminal;
                    }
                });

                if (themeData.hljs) {
                    switchHljsTheme(themeName);
                }
            } catch (e) {
                showToast('Error', '预览主题失败', 'error');
            }
        };

        const cancelPreview = () => {
            if (previewTheme.value) {
                // 恢复原主题
                const currentTheme = config.value.theme;
                tabs.value.forEach(tab => {
                    if (tab.term) {
                        tab.term.options.theme = THEME_PRESETS[currentTheme];
                    }
                });
                switchHljsTheme(currentTheme);
                previewTheme.value = null;
            }
        };

        const exportTheme = async (themeName) => {
            try {
                const res = await fetch(`/api/themes/export/${themeName}`);
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${themeName}_theme.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                showToast('Success', '主题导出成功', 'success');
            } catch (e) {
                showToast('Error', '导出主题失败', 'error');
            }
        };

        const importTheme = async (file) => {
            try {
                const text = await file.text();
                const themeData = JSON.parse(text);

                // 保存自定义主题
                const res = await fetch('/api/themes/custom', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify({ theme_data: themeData })
                });

                if (!res.ok) {
                    const error = await res.json();
                    throw new Error(error.detail || '导入失败');
                }

                await loadThemes();
                showToast('Success', `主题 "${themeData.displayName || themeData.name}" 导入成功`, 'success');
            } catch (e) {
                showToast('Error', `导入主题失败: ${e.message}`, 'error');
            }
        };

        const deleteTheme = async (themeName) => {
            if (!await requestConfirm('删除主题', `确定要删除主题 "${themeName}" 吗?`)) return;

            try {
                const res = await fetch(`/api/themes/custom/${themeName}`, {
                    method: 'DELETE',
                    headers: getHeaders()
                });

                if (!res.ok) {
                    const error = await res.json();
                    throw new Error(error.detail || '删除失败');
                }

                await loadThemes();
                showToast('Success', '主题删除成功', 'success');
            } catch (e) {
                showToast('Error', `删除主题失败: ${e.message}`, 'error');
            }
        };

        const openThemeMarket = async () => {
            showThemeMarket.value = true;
            await loadThemes();
        };

        const clearChat = async () => {
            if (!await requestConfirm('Clear Chat', 'Are you sure you want to clear the conversation history?')) return;
            chatHistory.value = [{ role: 'ai', content: 'Chat cleared. How can I help you?' }];
            saveSessions();
            showToast('Success', 'Chat history cleared', 'success');
        };

        const exportChat = () => {
            const text = chatHistory.value.map(m => `[${m.role.toUpperCase()}]\n${m.content}\n`).join('\n---\n\n');
            const blob = new Blob([text], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat-export-${new Date().toISOString().slice(0, 10)}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showToast('Success', 'Chat exported', 'success');
        };

        // --- 标签页 ---
        const createTab = () => {
            tabCounter++;
            const tabId = `term-${tabCounter}`;
            const tab = { id: tabId, name: `Terminal ${tabCounter}`, term: null, socket: null, fitAddon: null };
            tabs.value.push(tab);
            activeTabId.value = tabId;
            nextTick(() => initTerminal(tab));
        };

        const closeTab = (id) => {
            const index = tabs.value.findIndex(t => t.id === id);
            if (index === -1) return;
            const tab = tabs.value[index];
            if (tab.socket) tab.socket.close();
            if (tab.term) tab.term.dispose();
            tabs.value.splice(index, 1);
            if (tabs.value.length === 0) createTab();
            else if (activeTabId.value === id) activeTabId.value = tabs.value[tabs.value.length - 1].id;
        };

        const switchTab = (id) => {
            activeTabId.value = id;
            nextTick(() => {
                const tab = tabs.value.find(t => t.id === id);
                if (tab && tab.fitAddon) {
                    tab.fitAddon.fit();
                    tab.term.focus();
                }
            });
        };

        // --- 终端 ---
        const initTerminal = (tab) => {
            const containerId = `terminal-${tab.id}`;
            const terminalContainer = document.getElementById(containerId);
            if (!terminalContainer) return;

            const xterm = new Terminal({
                cursorBlink: true, fontSize: 14, fontFamily: 'Menlo, Monaco, Consolas, monospace',
                theme: THEME_PRESETS[config.value.theme] || THEME_PRESETS.dark
            });
            const fitAddon = new FitAddon();
            xterm.loadAddon(fitAddon);
            tab.term = xterm; tab.fitAddon = fitAddon;

            try {
                xterm.open(terminalContainer);
                terminalContainer.addEventListener('mousedown', () => xterm.focus());
                terminalContainer.addEventListener('click', () => xterm.focus());

                terminalContainer.addEventListener('contextmenu', (e) => {
                    const text = xterm.getSelection();
                    if (text && text.trim().length > 0) {
                        // 仅当有选择时阻止默认事件并显示自定义菜单
                        e.preventDefault();
                        contextMenu.value = { visible: true, x: e.clientX, y: e.clientY, text };
                    }
                    // 否则，允许原生浏览器上下文菜单出现
                });

                fitAddon.fit();
                xterm.focus();
            } catch (e) { console.error(e); }

            xterm.write(`\x1b[1;36mWelcome to AI-TERM v1.5 (${tab.name})\x1b[0m\r\n`);

            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            let wsUrl = `${protocol}//${window.location.host}/ws/terminal/${tab.id}`;
            if (config.value.access_token) wsUrl += `?token=${encodeURIComponent(config.value.access_token)}`;

            try {
                tab.socket = new WebSocket(wsUrl);
                tab.socket.onopen = () => { sendResize(tab); };
                tab.socket.onmessage = (e) => {
                    try {
                        // 检查后端系统消息 (JSON)
                        if (e.data.startsWith('{')) {
                            const msg = JSON.parse(e.data);
                            if (msg.type === 'system') {
                                if (msg.action === 'chat') {
                                    // 处理 :toChat
                                    if (!isChatMode.value) showSidebar.value = true;
                                    inputMessage.value = msg.content;
                                    nextTick(() => { document.querySelector('textarea')?.focus(); });
                                }
                                return; // 停止处理
                            }
                        }
                    } catch (err) { /* 非 JSON 或非系统消息，忽略 */ }
                    xterm.write(e.data);
                };
                xterm.onData(data => { if (tab.socket.readyState === 1) tab.socket.send(data); });

                // 快捷键拦截 (v2.5)
                xterm.onKey(e => {
                    if (e.domEvent.key === 'Enter') {
                        // 检查活动缓冲区行内容
                        const buffer = xterm.buffer.active;
                        const line = buffer.getLine(buffer.cursorY)?.translateToString(true).trim();

                        if (line && line.startsWith(':toChat ')) {
                            e.domEvent.preventDefault();
                            e.domEvent.stopPropagation();

                            // 发送特殊命令到后端
                            if (tab.socket.readyState === 1) {
                                tab.socket.send(JSON.stringify({
                                    type: 'cmd',
                                    data: line
                                }));

                                // 发送 Ctrl+C 到 PTY 以清除 Shell 中的行 
                                // (以免 Bash 报错命令未找到或挂起等待)
                                tab.socket.send('\x03');

                                // 视觉反馈
                                setTimeout(() => {
                                    xterm.write('\r\n\x1b[32m✔ Sent to Chat\x1b[0m\r\n');
                                    // 通常 Ctrl+C 后 Shell 会重打印提示符
                                }, 50);
                            }
                        }
                    }
                });
            } catch (e) { console.error(e); }
        };

        const sendResize = (tab) => {
            if (tab && tab.socket && tab.socket.readyState === 1) {
                const dims = tab.fitAddon.proposeDimensions();
                if (dims) {
                    tab.fitAddon.fit();
                    tab.socket.send(JSON.stringify({ cols: dims.cols, rows: dims.rows }));
                }
            }
        };

        // --- 聊天 & 文件 ---
        const loadFiles = async (path = '') => {
            try {
                const res = await fetch(`/api/fs/tree?path=${encodeURIComponent(path)}`, { headers: getHeaders() });
                return await res.json();
            } catch (e) { return []; }
        };
        const refreshFiles = async () => files.value = await loadFiles('');
        const loadDirectory = async (item) => item.children = await loadFiles(item.path);

        const executeCommand = (cmd) => {
            const tab = tabs.value.find(t => t.id === activeTabId.value);
            if (tab && tab.socket) {
                tab.socket.send(cmd + '\r');
                tab.term.focus();
            }
        };

        const saveFileAction = async (path, content) => {
            if (!await requestConfirm('Save File', `Save to ${path}?`)) return;
            try {
                await fetch('/api/fs/save', {
                    method: 'POST', headers: getHeaders(),
                    body: JSON.stringify({ path, content })
                });
                showToast('Success', `Saved ${path}`, 'success');
                await refreshFiles();
            } catch (e) { showToast('Error', e.message, 'error'); }
        };

        const stopGeneration = (confirmStop = true) => {
            if (!isLoading.value) return;

            if (confirmStop) {
                if (!confirm('确定要停止生成吗?\nAre you sure you want to stop generation?')) {
                    return;
                }
            }

            if (abortController) {
                abortController.abort();
                abortController = null;
            }

            isLoading.value = false;
            // Broadcast stop state
            broadcastChannel.postMessage({ type: 'generation_stopped' });
            broadcastChannel.postMessage({ type: 'loading_state', data: false });

            showToast('Info', 'Generation stopped by user', 'info');
        };

        // --- 聊天逻辑 ---
        const sendMessage = async (explicitId = null) => {
            // Fix: If called from event listener, explicitId is a PointerEvent. 
            // We need to ensure it's a string ID or null.
            if (explicitId && typeof explicitId !== 'string') {
                explicitId = null;
            }

            if ((!inputMessage.value.trim() && contextChips.value.length === 0) || isLoading.value) return;

            let finalMessage = inputMessage.value;
            if (contextChips.value.length > 0) {
                finalMessage += contextChips.value.map(c => `\n\n--- Context: ${c.label} ---\n${c.content}\n----------------\n`).join('');
            }

            // Use explicit ID if provided (from duplicate prevention), otherwise generate new unique ID
            const msgId = explicitId || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

            console.log('[Main] Processing sendMessage. ID:', msgId, 'Content:', inputMessage.value);

            // 修复 2: 主窗口也去重？
            // 通常主窗口是由于源，所以直接 push。
            const userMsg = {
                role: 'user',
                content: finalMessage,
                id: msgId,
                timestamp: Date.now()
            };

            try {
                chatHistory.value.push(userMsg);
            } catch (e) {
                console.error('[Main] Failed to push to history:', e);
            }

            // 广播新消息
            try {
                // Strip Proxies using JSON
                broadcastChannel.postMessage({ type: 'new_message', data: JSON.parse(JSON.stringify(userMsg)) });
            } catch (e) {
                console.error('[Main] Failed to broadcast message:', e);
            }

            // 修复 4: 通过同步清除弹出窗口中的 chips？
            // 或者在下次上下文更新时广播清除状态。
            // 实际上，我们应该在上下文变化时广播更新。

            inputMessage.value = '';
            contextChips.value = []; // Watcher will handle broadcast


            isLoading.value = true;
            console.log('[Main] Input cleared. isLoading set to true.');

            const aiMsgId = `msg_${Date.now()}_ai_${Math.random().toString(36).substr(2, 9)}`;
            const aiMsg = { role: 'ai', content: '', id: aiMsgId };
            const aiMsgIndex = chatHistory.value.push(aiMsg) - 1;

            try {
                broadcastChannel.postMessage({ type: 'new_message', data: aiMsg });
            } catch (e) { console.error('[Main] Failed to broadcast AI message:', e); }

            try {
                // ... map logic ...
                const messages = chatHistory.value.slice(0, -1).map(m => {
                    const role = m.role === 'ai' ? 'assistant' : m.role;
                    // 修复: 确保发送扩展后的消息用于统计，但 Prompt 逻辑已改进
                    if (m.role === 'user' && m.content === chatHistory.value[chatHistory.value.length - 2].content) {
                        return { role: 'user', content: finalMessage };
                    }
                    return { role: role, content: m.content };
                });
                // 修复上述映射问题：简化。
                // 重新映射所有:
                const apiMessages = chatHistory.value.slice(0, -1).map((m, idx) => {
                    let c = m.content;
                    if (idx === chatHistory.value.length - 2) c = finalMessage; // Last user message
                    return { role: m.role === 'ai' ? 'assistant' : 'user', content: c };
                });

                // 获取激活的提供商配置
                const activeProvider = config.value.activeProvider || 'deepseek';
                // Safe check for provider config
                if (!config.value.providers) {
                    throw new Error('No providers configuration found');
                }
                const providerConfig = config.value.providers[activeProvider];
                if (!providerConfig) {
                    throw new Error(`Provider config for ${activeProvider} not found`);
                }

                console.log('[Main] Sending message. Provider:', activeProvider, 'Config:', providerConfig);

                // Init AbortController
                abortController = new AbortController();

                // Broadcast loading state
                broadcastChannel.postMessage({ type: 'loading_state', data: true });

                const res = await fetch('/api/agent/chat', {
                    method: 'POST', headers: getHeaders(),
                    signal: abortController.signal,
                    body: JSON.stringify({
                        messages: apiMessages,
                        api_key: providerConfig.apiKey,
                        base_url: providerConfig.baseUrl,
                        model: providerConfig.model,
                        session_id: activeTabId.value || 'default'
                    })
                })

                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                // 正确解析 SSE 格式
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let content = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // 保留不完整的行

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') continue;
                            try {
                                const data = JSON.parse(dataStr);

                                // Handle Errors
                                if (data.error) {
                                    console.error('AI Error:', data.error);
                                    showToast('Error', data.error, 'error');

                                    // Broadcast error to popup
                                    broadcastChannel.postMessage({ type: 'generation_error', data: data.error });

                                    // Stop generation UI state
                                    isLoading.value = false;
                                    broadcastChannel.postMessage({ type: 'loading_state', data: false });
                                    break;
                                }

                                // Handle Metadata
                                if (data.meta) {
                                    console.log('Model Verification:', data.meta);
                                    chatHistory.value[aiMsgIndex].model = data.meta.model;
                                    showToast('Info', `Response from ${data.meta.model}`, 'info');
                                    continue;
                                }

                                const chunk = data.choices?.[0]?.delta?.content || '';
                                if (!chunk) continue;
                                content += chunk;

                                // Update last message content
                                const lastMsg = chatHistory.value[chatHistory.value.length - 1];
                                if (lastMsg) lastMsg.content = content;

                                // Broadcast update
                                broadcastChannel.postMessage({
                                    type: 'update_last_message',
                                    data: { content: content, id: aiMsgId }
                                });

                                scrollToBottom();
                            } catch (e) {
                                console.warn('SSE Parse Error:', e);
                            }
                        }
                    }
                }
            } catch (e) {
                if (e.name === 'AbortError') {
                    console.log('[Main] Generation aborted.');
                } else {
                    console.error('[Main] Chat Error:', e);
                    // Remove the empty AI message on error
                    chatHistory.value.pop();
                    broadcastChannel.postMessage({ type: 'remove_last_message' }); // Need to handle this in popup
                    showToast('Error', e.message, 'error');
                }
            } finally {
                isLoading.value = false;
                abortController = null;
                broadcastChannel.postMessage({ type: 'loading_state', data: false });
            }
        };

        // scrollToBottom is already defined above or we should merge them.
        // It seems I defined it inside the previous replace block at the end.
        // Let's remove this second definition if it exists in the original file at this location.
        // Converting to watch format.

        watch(chatHistory, (val) => {
            nextTick(() => {
                if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
            });
            // Auto-save logic
            if (saveTimer) clearTimeout(saveTimer);
            saveTimer = setTimeout(() => {
                saveChatHistory();
            }, 2000);
        }, { deep: true });
        // --- 渲染 ---
        const renderMarkdown = (text) => {
            if (typeof text !== 'string') return '';
            if (!window.marked) return text;
            const thinkRegex = /<thinking>([\s\S]*?)<\/thinking>/g;
            const processed = text.replace(thinkRegex, (m, c) =>
                `<details class="thinking-block" open><summary>Thinking Process</summary><div class="content">${c}</div></details>`
            );

            const renderer = new window.marked.Renderer();
            renderer.code = (entry, langIfString) => {
                let code = entry;
                let lang = langIfString;

                // 处理新的 marked.js 签名 (对象)
                if (typeof entry === 'object' && entry !== null) {
                    code = entry.text || entry.code || '';
                    lang = entry.lang || langIfString || '';
                }

                const codeId = `code-${Math.random().toString(36).substr(2, 9)}`;

                // 应用语法高亮
                let highlightedCode = code;
                if (window.hljs && lang) {
                    try {
                        const res = window.hljs.highlight(code, { language: lang });
                        if (res && res.value) highlightedCode = res.value;
                    } catch (e) {
                        // 回退到自动检测检查或仅转义
                        try {
                            const res = window.hljs.highlightAuto(code);
                            if (res && res.value) highlightedCode = res.value;
                        } catch (e2) {
                            highlightedCode = (code || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        }
                    }
                } else {
                    highlightedCode = (code || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                }

                // 基于图标的按钮
                let buttons = `
                    <button onclick="handleCodeAction('copy', '${codeId}')" class="text-gray-400 hover:text-white px-1.5 transition-colors" title="Copy">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button onclick="handleCodeAction('toterm', '${codeId}')" class="text-gray-400 hover:text-blue-400 px-1.5 transition-colors" title="Paste to Terminal">
                        <i class="fas fa-terminal"></i>
                    </button>
                `;

                if (['bash', 'sh', 'shell', 'python', 'py'].includes(lang)) {
                    buttons += `
                        <button onclick="handleCodeAction('run', '${codeId}')" class="text-gray-400 hover:text-red-400 px-1.5 transition-colors" title="Run in Terminal">
                            <i class="fas fa-play"></i>
                        </button>
                    `;
                }

                return `
                    <div class="code-block-wrapper relative group my-3 rounded-lg overflow-hidden border border-gray-700/50 hover:border-gray-600 transition-all">
                        <div class="code-header flex items-center justify-between px-4 py-1.5 bg-[#0f172a] border-b border-gray-700/50">
                            <span class="text-[10px] font-bold text-gray-500 uppercase tracking-wider">${lang || 'text'}</span>
                            <div class="flex items-center gap-1">
                                ${buttons}
                            </div>
                        </div>
                        <pre class="hljs bg-[#1e293b] p-4 overflow-x-auto text-sm m-0 leading-relaxed custom-scrollbar" data-code-id="${codeId}"><code class="language-${lang}">${highlightedCode}</code></pre>
                    </div>
                `;
            };
            return window.marked.parse(processed, { renderer });
        };

        // --- 交互 ---
        const handleSelection = () => {
            const sel = window.getSelection();
            if (sel && sel.toString().trim().length > 0) {
                const anchor = sel.anchorNode.nodeType === 3 ? sel.anchorNode.parentNode : sel.anchorNode;
                // Check if selection is inside chat or readable content
                if (anchor.closest('.chat-bubble') || anchor.closest('.prose') || anchor.closest('.markdown-body')) {
                    // Check if not inside an input/textarea
                    if (!anchor.closest('textarea') && !anchor.closest('input')) {
                        const range = sel.getRangeAt(0);
                        const rect = range.getBoundingClientRect();

                        // 计算位置：居中显示在选区上方
                        // 工具栏尺寸：宽 ~150px，高 ~40px
                        const toolbarWidth = 150;
                        const toolbarHeight = 40;

                        let left = rect.left + (rect.width / 2) - (toolbarWidth / 2); // 居中工具栏
                        let top = rect.top - toolbarHeight - 5; // 上方 5px 间隙

                        // 边界检查 - 确保工具栏在视口内
                        if (left < 10) left = 10; // 最小左边距
                        if (left + toolbarWidth > window.innerWidth - 10) {
                            left = window.innerWidth - toolbarWidth - 10; // 最大右边距
                        }
                        if (top < 10) {
                            // 如果太靠近顶部，显示在选区下方
                            top = rect.bottom + 5;
                        }
                        // 检查工具栏是否超出底部
                        if (top + toolbarHeight > window.innerHeight - 10) {
                            top = window.innerHeight - toolbarHeight - 10;
                        }

                        selectionOverlay.value = {
                            visible: true,
                            x: left,
                            y: top,
                            type: 'chat',
                            text: sel.toString()
                        };
                        return;
                    }
                }
            }
            // 不要立即隐藏，由外部 mousedown 处理
        };

        const sendToChat = () => {
            const { text, type } = selectionOverlay.value;
            if (text.trim()) {
                const lines = text.split('\n').length;
                contextChips.value.push({ label: type === 'term' ? `Terminal (${lines}L)` : `Selection (${lines}L)`, content: text, type });
            }
            selectionOverlay.value.visible = false;
        };

        const copySelection = async () => {
            const { text } = selectionOverlay.value;
            if (text) {
                await navigator.clipboard.writeText(text);
                showToast('Success', 'Copied to clipboard', 'success');
                selectionOverlay.value.visible = false;
            }
        };

        const sendToTerm = () => {
            const { text } = selectionOverlay.value;
            if (text) {
                const tab = tabs.value.find(t => t.id === activeTabId.value);
                if (tab && tab.socket && tab.socket.readyState === 1) {
                    tab.socket.send(text);
                    tab.term.focus();
                    showToast('Success', 'Sent to terminal', 'info');
                } else {
                    showToast('Error', 'No active terminal', 'error');
                }
                selectionOverlay.value.visible = false;
            }
        };
        // --- Context Menu Actions ---
        // --- 上下文菜单 & 代码操作 ---
        const chipCounters = ref({}); // 跟踪每个终端标签页的 chip 数量

        const contextAction = async (action) => {
            const { text } = contextMenu.value;
            if (!text) return;

            if (action === 'toChat') {
                // 获取当前终端标签页 ID
                const tabId = activeTabId.value || 1;

                // 增加此标签页的计数器
                if (!chipCounters.value[tabId]) {
                    chipCounters.value[tabId] = 0;
                }
                chipCounters.value[tabId]++;

                // 创建格式为 @term-{tabId}-{count} 的 chip
                const chipLabel = `@term-${tabId}-${chipCounters.value[tabId]}`;
                const chipData = {
                    label: chipLabel,
                    content: text,
                    type: 'term',
                    tabId: tabId,
                    count: chipCounters.value[tabId]
                };

                // 如果弹出窗口打开，路由到弹出窗口
                // 如果弹出窗口打开，通过广播通道发送
                if (isPopupOpen.value) {
                    broadcastChannel.postMessage({
                        type: 'trigger_input',
                        content: text,
                        chip: chipData
                    });
                    showToast('Success', '已发送到弹出窗口输入框', 'success');
                } else {
                    // 添加到当前窗口
                    contextChips.value.push(chipData);
                }

                // 聚焦输入区域
                nextTick(() => {
                    const textarea = document.querySelector('textarea');
                    if (textarea) textarea.focus();
                });
            } else if (action === 'copy') {
                navigator.clipboard.writeText(text);
                showToast('Success', 'Copied to clipboard', 'success');
            } else if (action === 'run') {
                await safelyRunCommand(text.trim());
            }
            contextMenu.value.visible = false;
        };

        const handleCodeAction = async (action, codeId) => {
            const codeBlock = document.querySelector(`pre[data-code-id="${codeId}"] code`);
            if (!codeBlock) return;
            const code = codeBlock.innerText;

            // 检查是否在弹出窗口中
            if (window.opener && !window.opener.closed) {
                if (action === 'toterm') {
                    window.opener.pasteToTerminal(code);
                    showToast('Success', 'Pasted to parent terminal', 'info');
                    return;
                } else if (action === 'run') {
                    window.opener.runInTerminal(code);
                    showToast('Success', 'Running in parent terminal', 'info');
                    return;
                }
            }

            // 主窗口的常规处理
            if (action === 'copy') {
                navigator.clipboard.writeText(code);
                showToast('Success', 'Code copied', 'success');
            } else if (action === 'toterm') {
                const tab = tabs.value.find(t => t.id === activeTabId.value);
                if (tab && tab.socket) {
                    tab.socket.send(code);
                    tab.term.focus();
                    showToast('Success', 'Pasted to terminal', 'info');
                } else {
                    showToast('Error', 'No active terminal', 'error');
                }
            } else if (action === 'run') {
                await safelyRunCommand(code.trim());
            }
        };

        // 暴露给 window 以供 marked 渲染器中的内联 onclick 处理程序使用
        window.handleCodeAction = handleCodeAction;

        // 暴露全局钩子以供弹出窗口集成
        window.pasteToTerminal = (code) => {
            const tab = tabs.value.find(t => t.id === activeTabId.value);
            if (tab && tab.socket) tab.socket.send(code);
        };

        window.runInTerminal = async (code) => {
            await safelyRunCommand(code.trim());
        };

        // 处理上下文菜单外部的点击
        const handleGlobalClick = (e) => {
            if (contextMenu.value.visible) {
                const menuEl = document.querySelector('.terminal-context-menu');
                if (menuEl && !menuEl.contains(e.target)) {
                    contextMenu.value.visible = false;
                }
            }
        };

        // --- 安全运行逻辑 ---
        const safelyRunCommand = async (code) => {
            // 危险命令模式
            const DANGEROUS_PATTERNS = [
                { pattern: /rm\s+-rf\s+\//, warning: '删除系统根目录' },
                { pattern: /:\(\)\{\s*:\|:\&\s*\};:/, warning: 'Fork 炸弹攻击' },
                { pattern: /dd\s+if=/, warning: '直接磁盘写入操作' },
                { pattern: /mkfs\./, warning: '格式化文件系统' },
                { pattern: /sudo\s+rm/, warning: '使用提升的权限删除文件' },
                { pattern: />\/dev\/sd[a-z]/, warning: '写入磁盘设备' },
                { pattern: /chmod\s+-R\s+777/, warning: '不安全的权限更改' }
            ];

            // 检查危险模式
            const dangerousMatch = DANGEROUS_PATTERNS.find(p => p.pattern.test(code));
            let confirmMessage = `确定要运行此命令吗?\n\n${code.substring(0, 200)}${code.length > 200 ? '...' : ''}`;

            if (dangerousMatch) {
                confirmMessage = `⚠️ 警告: 潜在的危险命令\n\n此命令可能: ${dangerousMatch.warning}\n\n命令: ${code.substring(0, 150)}${code.length > 150 ? '...' : ''}\n\n您绝对确定要执行此操作吗?`;
            }

            const confirmed = await requestConfirm(
                dangerousMatch ? '⚠️ 危险命令' : '执行命令',
                confirmMessage
            );
            if (!confirmed) return;

            const tab = tabs.value.find(t => t.id === activeTabId.value);
            if (tab && tab.socket && tab.socket.readyState === 1) {
                // 审计日志
                const auditEntry = {
                    timestamp: new Date().toISOString(),
                    command: code,
                    dangerous: !!dangerousMatch,
                    terminal: tab.name
                };
                console.log('[AUDIT]', auditEntry);

                tab.socket.send(code + '\n');
                showToast('Success', dangerousMatch ? '⚠️ 已执行危险命令' : '命令已执行', dangerousMatch ? 'warning' : 'success');
            } else {
                showToast('Error', '无活动的终端连接', 'error');
            }
        };

        // --- 规则逻辑 ---
        const loadRules = async () => {
            // Migration: Clear legacy localStorage if present
            if (localStorage.getItem('ai-term-rules')) {
                console.log('Migrating rules from localStorage to backend...');
                localStorage.removeItem('ai-term-rules');
                Object.keys(localStorage).forEach(key => {
                    if (key.startsWith('ai-term-rule-content-')) {
                        localStorage.removeItem(key);
                    }
                });
            }

            try {
                const response = await fetch('/api/rules');
                if (response.ok) {
                    const rules = await response.json();
                    // rules is array of objects {name, is_default, description}
                    rulesList.value = rules.map(r => r.name);

                    // Recover active rule or default
                    const storedActive = localStorage.getItem('ai-term-active-rule');
                    if (storedActive && rulesList.value.includes(storedActive)) {
                        activeRule.value = storedActive;
                    } else {
                        // Optional: default to something if needed
                    }
                }
            } catch (e) {
                console.error("Failed to load rules:", e);
                showToast('Error', '加载模板列表失败', 'error');
            }
        };

        const selectRule = async (name) => {
            selectedRuleName.value = name;
            try {
                const response = await fetch(`/api/rules/${name}`);
                if (response.ok) {
                    const ruleData = await response.json();
                    ruleContent.value = ruleData.content || '';
                } else {
                    showToast('Error', '加载模板内容失败', 'error');
                }
            } catch (e) {
                console.error(`Failed to load rule ${name}:`, e);
                ruleContent.value = '';
            }
        };

        const createRule = () => { showNewRuleModal.value = true; newRuleName.value = ''; };

        const confirmCreateRule = async () => {
            const name = newRuleName.value.trim();
            if (!name) return;

            try {
                const response = await fetch('/api/rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, content: '', description: '' })
                });

                if (response.ok) {
                    await loadRules();
                    showNewRuleModal.value = false;
                    selectRule(name);
                    showToast('Success', `模板 "${name}" 已创建`, 'success');
                } else {
                    const err = await response.json();
                    showToast('Error', err.detail || '创建失败', 'error');
                }
            } catch (e) {
                showToast('Error', '创建请求失败', 'error');
            }
        };

        const saveRule = async () => {
            if (!selectedRuleName.value) return;
            if (selectedRuleName.value === 'default') {
                showToast('Error', '无法修改默认模板', 'error');
                return;
            }

            try {
                const response = await fetch(`/api/rules/${selectedRuleName.value}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: ruleContent.value })
                });

                if (response.ok) {
                    showToast('Success', '模板已保存', 'success');
                } else {
                    const err = await response.json();
                    showToast('Error', err.detail || '保存失败', 'error');
                }
            } catch (e) {
                showToast('Error', '保存请求失败', 'error');
            }
        };

        const deleteRule = async (name) => {
            if (name === 'default') { showToast('Error', '无法删除默认模板', 'error'); return; }
            if (!await requestConfirm('删除模板', `确定要删除 "${name}" 吗?`)) return;

            try {
                const response = await fetch(`/api/rules/${name}`, { method: 'DELETE' });
                if (response.ok) {
                    if (selectedRuleName.value === name) selectedRuleName.value = null;
                    if (activeRule.value === name) {
                        activeRule.value = null;
                        localStorage.removeItem('ai-term-active-rule');
                    }
                    await loadRules();
                    showToast('Success', '模板已删除', 'success');
                } else {
                    const err = await response.json();
                    showToast('Error', err.detail || '删除失败', 'error');
                }
            } catch (e) {
                showToast('Error', '删除请求失败', 'error');
            }
        };

        const activateRule = (name) => {
            activeRule.value = name;
            if (name) localStorage.setItem('ai-term-active-rule', name);
            else localStorage.removeItem('ai-term-active-rule');
            showToast('Info', name ? `当前激活模板: ${name}` : '模板已停用', 'info');
        };

        // --- Pop Out Chat ---
        // --- 弹出窗口管理 ---
        const popupWindow = ref(null);
        const isPopupOpen = ref(false);

        const openPopupChat = () => {
            if (popupWindow.value && !popupWindow.value.closed) {
                popupWindow.value.focus();
                return;
            }

            // 打开弹出窗口
            const width = 800;
            const height = 600;
            const left = (screen.width - width) / 2;
            const top = (screen.height - height) / 2;

            popupWindow.value = window.open(
                '/popup-chat',
                'AI-TERM Chat',
                `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
            );

            if (popupWindow.value) {
                isPopupOpen.value = true;

                // 监控弹出窗口关闭
                const checkClosed = setInterval(() => {
                    if (popupWindow.value && popupWindow.value.closed) {
                        isPopupOpen.value = false;
                        clearInterval(checkClosed);
                        popupWindow.value = null;
                    }
                }, 500);

                // 发送初始聊天记录到弹出窗口
                setTimeout(() => {
                    if (popupWindow.value && !popupWindow.value.closed) {
                        popupWindow.value.postMessage({
                            type: 'initChat',
                            chatHistory: chatHistory.value,
                            config: config.value
                        }, '*');
                    }
                }, 1000);
            }
        };

        // 监听弹出窗口消息
        window.addEventListener('message', (event) => {
            if (event.data.type === 'syncChat') {
                // 从弹出窗口同步聊天记录
                chatHistory.value = event.data.messages;
                saveCurrentSession();
            } else if (event.data.type === 'addChipToPopup') {
                // 确认 chip 已发送到弹出窗口
                console.log('Chip sent to popup:', event.data.chip);
            }
        });


        // 调整大小
        const startResize = (s) => { isResizing.value = s; document.body.style.cursor = 'col-resize'; document.body.classList.add('select-none'); };
        const handleResize = (e) => {
            if (isResizing.value === 'left') sidebarWidth.value = Math.max(200, Math.min(e.clientX, 500));
            if (isResizing.value === 'right') agentWidth.value = Math.max(300, Math.min(window.innerWidth - e.clientX, 800));
        };
        const stopResize = () => { if (isResizing.value) { isResizing.value = null; document.body.style.cursor = ''; document.body.classList.remove('select-none'); window.dispatchEvent(new Event('resize')); } };
        const trackMouse = (e) => { if (isResizing.value) handleResize(e); };

        // 历史记录
        const saveSessions = () => localStorage.setItem('ai-term-sessions', JSON.stringify(chatSessions.value));
        const initHistory = () => {
            try { chatSessions.value = JSON.parse(localStorage.getItem('ai-term-sessions') || '[]'); } catch (e) { }
            if (chatSessions.value.length === 0) createNewSession();
            else loadSession(localStorage.getItem('ai-term-current-id') || chatSessions.value[0].id);
        };
        const createNewSession = () => {
            const id = Date.now().toString();
            chatSessions.value.unshift({ id, title: 'New Chat', messages: [{ role: 'ai', content: 'Hello! I am your AI Terminal Assistant.' }] });
            loadSession(id);
            saveSessions();
        };
        const loadSession = (id) => {
            const s = chatSessions.value.find(x => x.id === id);
            if (s) { currentSessionId.value = id; chatHistory.value = s.messages; localStorage.setItem('ai-term-current-id', id); showHistory.value = false; scrollToBottom(); }
        };
        const deleteSession = (e, id) => {
            e.stopPropagation();
            const idx = chatSessions.value.findIndex(s => s.id === id);
            if (idx > -1) {
                chatSessions.value.splice(idx, 1);
                saveSessions();
                if (chatSessions.value.length === 0) createNewSession();
                else if (currentSessionId.value === id) loadSession(chatSessions.value[0].id);
            }
        };

        watch(chatHistory, (val) => {
            if (currentSessionId.value) {
                const s = chatSessions.value.find(x => x.id === currentSessionId.value);
                if (s) { s.messages = val; if (val[1] && val[1].role === 'user') s.title = val[1].content.slice(0, 30); saveSessions(); }
            }
        }, { deep: true });

        // 全局变量
        window.typeToTerm = (c) => tabs.value.find(t => t.id === activeTabId.value)?.socket?.send(c);
        window.runInTerm = (c) => tabs.value.find(t => t.id === activeTabId.value)?.socket?.send(c + '\n');
        window.pasteToTerminal = (c) => {
            const tab = tabs.value.find(t => t.id === activeTabId.value);
            if (tab && tab.socket) tab.socket.send(c);
        };
        window.saveFileAction = saveFileAction;
        window.executeCommand = executeCommand;

        // 状态
        const statusText = ref('Disconnected');
        const statusColor = ref('bg-red-500');

        // 输入框自动调整大小
        const textAreaHeight = ref('50px');
        const autoResizeTextArea = (e) => {
            const el = e.target;
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 200) + 'px';
            textAreaHeight.value = el.style.height;
        };

        watch(inputMessage, (val) => {
            if (!val) textAreaHeight.value = '50px';
        });

        // --- 辅助函数 ---
        // ... (existing helpers)

        // 模拟状态检查
        const checkStatus = async () => {
            try {
                // simple ping or just check if websocket is open
                const isConnected = tabs.value.some(t => t.socket && t.socket.readyState === 1);
                if (isConnected) {
                    document.getElementById('status-indicator').classList.remove('bg-red-500', 'shadow-[0_0_8px_rgba(239,68,68,0.5)]');
                    document.getElementById('status-indicator').classList.add('bg-emerald-500', 'shadow-[0_0_8px_rgba(16,185,129,0.5)]');
                    document.getElementById('status-text').textContent = 'Connected';
                    document.getElementById('status-text').classList.replace('text-gray-500', 'text-emerald-500');
                } else {
                    document.getElementById('status-indicator').classList.remove('bg-emerald-500', 'shadow-[0_0_8px_rgba(16,185,129,0.5)]');
                    document.getElementById('status-indicator').classList.add('bg-red-500', 'shadow-[0_0_8px_rgba(239,68,68,0.5)]');
                    document.getElementById('status-text').textContent = 'Disconnected';
                    document.getElementById('status-text').classList.replace('text-emerald-500', 'text-gray-500');
                }
            } catch (e) { }
        };

        setInterval(checkStatus, 2000);

        const validateModelConfig = async () => {
            if (!config.value.base_url) return;

            // Deepseek 自动修复
            if (config.value.base_url.includes('deepseek.com') && config.value.model.includes('gpt')) {
                const confirmed = await requestConfirm(
                    '配置不匹配检测',
                    '检测到您使用的是 DeepSeek API 但模型名为 GPT。\n这可能会导致 400 错误。\n\n是否自动切换为 deepseek-chat 模型？'
                );

                if (confirmed) {
                    config.value.model = 'deepseek-chat';
                    await saveConfig();
                    showToast('已自动修复', '模型已切换为 deepseek-chat', 'success');
                }
            }
        };

        onMounted(async () => {
            // 检查 URL 参数中的模式
            const params = new URLSearchParams(window.location.search);
            if (params.get('mode') === 'chat') {
                isChatMode.value = true;
                showSidebar.value = false; // 隐藏文件资源管理器
                // 我们将根据 isChatMode 在模板中处理特定布局
            }

            try {
                // 首先加载聊天记录
                await loadChatHistory();

                // 留出时间填充历史记录
                await nextTick();

                createTab();
                initHistory();
                await refreshFiles();
                await loadConfig();
                loadRules();

                // 使用外部定义的函数验证模型配置
                await validateModelConfig();

                // 应用主题
                if (config.value && config.value.theme) {
                    await applyTheme(config.value.theme);
                }

                // 页面卸载前保存聊天记录
                window.addEventListener('beforeunload', () => {
                    saveChatHistory();
                });
            } catch (e) {
                console.error("CRITICAL ERROR in onMounted:", e);
            }

            document.addEventListener('mouseup', (e) => {
                stopResize();
                // 延迟执行以确保选区已更新
                setTimeout(handleSelection, 10);
            });
            document.addEventListener('mousedown', (e) => {
                // 如果点击的不是工具栏或其子元素，则隐藏工具栏
                if (selectionOverlay.value.visible && !e.target.closest('.selection-toolbar')) {
                    selectionOverlay.value.visible = false;
                }
            });
            document.addEventListener('mousemove', trackMouse);
            document.addEventListener('click', handleGlobalClick);

            // ESC 键关闭上下文菜单
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && contextMenu.value.visible) {
                    contextMenu.value.visible = false;
                }
            });

            window.addEventListener('resize', () => sendResize(tabs.value.find(t => t.id === activeTabId.value)));

            // 代码块按钮处理程序 (事件委托)
            document.addEventListener('click', async (e) => {
                const btn = e.target.closest('.code-action-icon-btn');
                if (!btn) return;

                const codeId = btn.dataset.codeId;
                const codeBlock = document.querySelector(`pre[data-code-id="${codeId}"] code`);
                if (!codeBlock) return;

                const code = codeBlock.textContent;
                const icon = btn.querySelector('i');
                const originalClass = icon.className;

                try {
                    if (btn.classList.contains('copy-btn')) {
                        // 复制到剪贴板
                        await navigator.clipboard.writeText(code);
                        icon.className = 'fas fa-check';
                        btn.classList.add('success');
                        setTimeout(() => {
                            icon.className = originalClass;
                            btn.classList.remove('success');
                        }, 2000);
                        showToast('Success', '代码已复制到剪贴板', 'success');
                    }
                    else if (btn.classList.contains('toterm-btn')) {
                        // 发送到终端
                        const tab = tabs.value.find(t => t.id === activeTabId.value);
                        if (tab && tab.socket && tab.socket.readyState === 1) {
                            tab.socket.send(code); // 发送原始文本
                            icon.className = 'fas fa-check';
                            btn.classList.add('success');
                            setTimeout(() => {
                                icon.className = originalClass;
                                btn.classList.remove('success');
                            }, 1500);
                            showToast('Success', '代码已发送到终端', 'success');
                        } else {
                            showToast('Error', '无活动的终端连接', 'error');
                        }
                    }
                    else if (btn.classList.contains('run-btn')) {
                        // 在终端中运行 (带安全确认)
                        const confirmed = await requestConfirm(
                            '执行命令',
                            `确定要运行此命令吗?\n\n${code.substring(0, 200)}${code.length > 200 ? '...' : ''}`
                        );
                        if (!confirmed) return;

                        const tab = tabs.value.find(t => t.id === activeTabId.value);
                        if (tab && tab.socket && tab.socket.readyState === 1) {
                            tab.socket.send(code + '\n'); // 发送原始文本
                            icon.className = 'fas fa-spinner fa-spin';
                            setTimeout(() => {
                                icon.className = 'fas fa-check';
                                btn.classList.add('success');
                                setTimeout(() => {
                                    icon.className = originalClass;
                                    btn.classList.remove('success');
                                }, 1500);
                            }, 500);
                            showToast('Success', '命令已执行', 'success');
                        } else {
                            showToast('Error', '无活动的终端连接', 'error');
                        }
                    }
                } catch (err) {
                    console.error('Failed to handle code action:', err);
                    showToast('Error', '执行操作失败', 'error');
                }
            });

            watch(() => config.value.theme, (t) => {
                // 更新终端主题
                tabs.value.forEach(tab => { if (tab.term) tab.term.options.theme = THEME_PRESETS[t]; });
                // 同步更新代码高亮主题
                switchHljsTheme(t);
            });

            // 初始高度
            textAreaHeight.value = '50px';
        });

        onUnmounted(() => {
            document.removeEventListener('selectionchange', handleSelection);
            document.removeEventListener('mousemove', trackMouse);
            document.removeEventListener('mouseup', stopResize);
            document.removeEventListener('click', handleGlobalClick);
        });

        return {
            // 状态
            config, tabs, activeTabId, chatHistory, currentSessionId, chatSessions,
            showSidebar, showSettings, showHistory, showRules, showThemes, showThemeMarket, isChatMode, activeSettingsTab,
            files, contextMenu, contextChips, confirmModal, agentWidth, sidebarWidth,
            popupWindow, isPopupOpen, chatContainer, isLoading, showApiKey,
            rulesList, selectedRuleName, ruleContent, activeRule, showNewRuleModal, newRuleName,
            toasts, selectionOverlay, textAreaHeight, showAgent, currentModel, inputMessage, currentModelName,
            // 方法
            sendMessage, clearChat, createNewSession, loadSession, deleteSession,
            showToast, removeToast, closeConfirm, removeChip, clearChips, openPopupChat, exportChat,
            saveConfig, createTab, closeTab, switchTab,
            loadDirectory, refreshFiles, contextAction, applyTheme, toggleTheme,
            renderMarkdown, startResize, stopResize, autoResizeTextArea,
            loadDirectory, refreshFiles,
            toggleTheme, openThemeMarket,
            loadThemes, applyTheme, previewThemeAction, cancelPreview, exportTheme, importTheme, deleteTheme,
            clearChat, exportChat,
            createTab, closeTab, switchTab,
            sendMessage, openPopupChat, createNewSession, loadSession, deleteSession,
            saveConfig,
            // 规则
            createRule, deleteRule, saveRule, selectRule, activateRule, confirmCreateRule,
            // Chips (标签)
            removeChip,
            // 工具
            renderMarkdown, showToast, removeToast, requestConfirm, closeConfirm,
            // 选择操作
            sendToTerm, copySelection, sendToChat,
            // 模型管理
            handleModelChange,
            handleRemoteCommand,
            stopGeneration
        };
    }
}).mount('#app');
