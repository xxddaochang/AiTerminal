-- AI-TERM 数据库 Schema v2.0
-- 创建时间: 2026-02-08

-- ============================================
-- 规则表 (Rules)
-- ============================================
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,              -- 规则名称 (唯一)
    file_path TEXT NOT NULL,                -- 文件路径 (~/.cache/ai-term/rules/{name}.md)
    description TEXT,                       -- 规则描述
    is_default BOOLEAN DEFAULT 0,           -- 是否为默认规则
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- AI 模型配置表 (AI Modules Tab)
-- ============================================
CREATE TABLE IF NOT EXISTS ai_modules_tab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT UNIQUE NOT NULL,     -- 提供商名称 (deepseek, qwen, doubao)
    display_name TEXT NOT NULL,             -- 显示名称 (深度求索, 通义千问, 豆包)
    api_key TEXT,                           -- API 密钥
    base_url TEXT,                          -- API 基础 URL
    default_model TEXT,                     -- 默认模型
    available_models TEXT,                  -- 可用模型列表 (JSON array)
    custom_params TEXT,                     -- 自定义参数 (JSON object)
    is_active BOOLEAN DEFAULT 1,            -- 是否激活
    sort_order INTEGER DEFAULT 0,           -- 排序顺序
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 索引
-- ============================================
CREATE INDEX IF NOT EXISTS idx_rules_name ON rules(name);
CREATE INDEX IF NOT EXISTS idx_rules_default ON rules(is_default);
CREATE INDEX IF NOT EXISTS idx_modules_provider ON ai_modules_tab(provider_name);
CREATE INDEX IF NOT EXISTS idx_modules_active ON ai_modules_tab(is_active);
CREATE INDEX IF NOT EXISTS idx_modules_sort ON ai_modules_tab(sort_order);

-- ============================================
-- 初始数据
-- ============================================

-- 插入默认规则记录
INSERT OR IGNORE INTO rules (name, file_path, description, is_default) 
VALUES ('default', '~/.cache/ai-term/rules/default.md', '系统默认规则', 1);

-- 插入默认模型配置
INSERT OR IGNORE INTO ai_modules_tab (provider_name, display_name, base_url, default_model, available_models, sort_order) 
VALUES 
    ('deepseek', '深度求索 DeepSeek', 'https://api.deepseek.com', 'deepseek-chat', '["deepseek-chat", "deepseek-coder"]', 1),
    ('qwen', '通义千问 Qwen', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-turbo', '["qwen-turbo", "qwen-plus", "qwen-max"]', 2),
    ('doubao', '豆包 Doubao', 'https://ark.cn-beijing.volces.com/api/v3', 'doubao-pro-4k', '["doubao-pro-4k", "doubao-pro-32k"]', 3);
