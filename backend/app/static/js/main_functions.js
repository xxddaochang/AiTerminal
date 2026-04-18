// 选择操作函数 - 将添加到 main.js setup()

const copySelection = async () => {
    const { text } = selectionOverlay.value;
    if (text) {
        await navigator.clipboard.writeText(text);
        showToast('Success', '已复制到剪贴板', 'success');
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
            showToast('Success', '已发送到终端', 'info');
        } else {
            showToast('Error', '无活动的终端', 'error');
        }
        selectionOverlay.value.visible = false;
    }
};
