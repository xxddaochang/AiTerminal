<div align="center">

# AI-TERM

**AI 增强型 Web 终端 —— 文件树 · Shell · AI 助手，三栏并列。**

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE-AGPL-3.0.txt)
[![Commercial License](https://img.shields.io/badge/license-Commercial-green.svg)](./COMMERCIAL-LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)

[English](./README.md) · [简体中文](./README.zh-CN.md)

</div>

---

## 项目定位

AI-TERM 是一个**单用户、自托管**的 Web 应用，把开发者最常用的三块界面拼进同一个浏览器窗口：

- **左栏**：工作目录的沙盒化文件树。读写接口做了路径穿越防御、文件大小限制、符号链接越界检测。
- **中栏**：基于 WebSocket 的真 PTY Shell，Unix 下走 `ptyprocess`，Windows 下走 `pywinpty`。
- **右栏**：流式 AI 助手，对接任意 OpenAI 兼容端点（DeepSeek、通义千问 / DashScope、豆包 / 火山方舟、OpenAI 或你自己的代理）。

它的目标是**本机单人使用**：一个 token、一个浏览器、一台机器。不是多租户产品。

## 核心特性

- **流式对话（SSE）** 对接 OpenAI 兼容 API，按 provider 独立配置 `apiKey` / `apiBase` / `model`
- **PTY Shell** 支持 ANSI 色彩、Tab 补全、精准 cwd 追踪（Linux 用 `/proc/<pid>/cwd`，macOS 用 `lsof`）
- **访问令牌鉴权** 三通道（Header / Query / Cookie）。HTML 入口自动下发 `HttpOnly` + `SameSite=Strict` Cookie，浏览器端零改动
- **规则 / 主题 / 聊天记录持久化** 存在 `~/.cache/ai-term/`，目录 0700、文件 0600
- **可选 WebDAV 云同步** 使用 AES-256-GCM + PBKDF2 加密凭据
- **插件机制** `plugins/<名称>/__init__.py` 可向 FastAPI 动态注入路由
- **默认安全姿态** 路径穿越防御、日志敏感字段脱敏、配置原子写入、受限异步队列

## 截图

_发布前补上截图或 GIF。_

## 快速开始

### 环境要求

- Python 3.10 或更高
- macOS / Linux / Windows 10+
- 现代浏览器（Chrome / Edge / Firefox / Safari）
- 至少一个受支持厂商的 API Key（DeepSeek / 通义千问 / 豆包 / OpenAI 等）

### 安装

```bash
git clone https://github.com/<你的-GitHub-用户名>/AI-TERM.git
cd AI-TERM
./setup.sh             # 创建 venv、安装依赖、macOS 自动补装 ptyprocess
```

### 配置

复制模板到用户目录，填入任意一个 provider 的 API Key：

```bash
mkdir -p ~/.ai-term
cp config.json.example ~/.ai-term/config.json
chmod 600 ~/.ai-term/config.json
$EDITOR ~/.ai-term/config.json   # 填写 providers.<名称>.apiKey
```

`access_token` 字段可以留空或删除——服务器首次启动会自动生成一个并写回同一个文件。

### 启动

```bash
./run.sh
```

浏览器打开 `http://127.0.0.1:8080/`。首次加载页面时后端会在响应里 `Set-Cookie: ai_term_token=...`，之后所有 `fetch` 和 WebSocket 请求都会自动带上。

## 配置说明

### `~/.ai-term/config.json`（用户级）

```jsonc
{
  "access_token": "首次启动会自动生成",
  "activeProvider": "deepseek",
  "providers": {
    "deepseek": { "apiKey": "...", "apiBase": "https://api.deepseek.com/v1", "model": "deepseek-chat" },
    "qwen":     { "apiKey": "...", "apiBase": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus" }
  },
  "sync": { "enabled": false, "url": "...", "username": "...", "password_encrypted": "..." }
}
```

完整带注释的模板见 [`config.json.example`](./config.json.example)。

### `backend/app/config/ai-term.conf`（服务端级）

INI 格式；所有路径支持 `~` 展开；字段含义见文件内行级注释。

### 环境变量

| 变量 | 用途 | 默认值 |
|---|---|---|
| `AI_TERM_HOST` | Uvicorn 绑定地址 | `127.0.0.1` |
| `AI_TERM_PORT` | Uvicorn 端口 | `8080` |
| `AI_TERM_RELOAD` | 启用热重载（开发用） | 未设置 |
| `AI_TERM_CORS_ORIGINS` | 逗号分隔的跨域白名单；设 `*` 会自动关闭 credentials | localhost:8080 白名单 |
| `AI_TERM_LEGACY_OPEN` | 设为 `1` 跳过 token 鉴权（仅应急） | 未设置 |
| `AI_TERM_MASTER_PASSWORD` | WebDAV 同步凭据加密主密码 | 未设置时走派生路径 + 随机盐 |

## 目录结构

```
AI-TERM/
├── backend/
│   └── app/
│       ├── api/            # HTTP 路由模块 (files、…)
│       ├── core/           # auth、plugin 加载器
│       ├── database/       # SQLite 管理与 schema
│       ├── services/       # agent、pty、rule、theme、sync、crypto、file、model
│       ├── static/         # CSS / JS / 主题
│       ├── templates/      # Jinja2 模板 (index / popup-chat)
│       ├── utils/          # 配置解析
│       └── main.py         # FastAPI 入口 + WebSocket
├── plugins/                # 即插即用的 Python 插件
├── docs/                   # 架构、PRD、用户手册
├── tests/                  # pytest 与验证脚本
├── setup.sh / run.sh       # macOS / Linux 安装 & 启动
└── config.json.example     # 用户级配置模板
```

## 安全模型

AI-TERM **没有**按多租户生产标准做加固，它的威胁模型假设是"本机可信用户"。关键控制：

- `/`、`/popup-chat`、`/static/*` 之外的所有 HTTP API 都要求合法 access token（Header / Query / Cookie 三选一）
- WebSocket 握手同样校验 token（Query 参数或 Cookie）
- 文件服务根目录锁定在启动 cwd；所有路径用 `realpath` + `commonpath` 解析；越界符号链接被拒
- 敏感字段（`apiKey`、`access_token`、`password_*`）在任何返回配置的接口里都会被剥离
- 配置原子写入（tmp + `os.replace`）并 `chmod 0600`；配置目录 `chmod 0700`
- WebDAV 同步凭据用 AES-256-GCM 加密；密钥由主密码（opt-in） + 随机 16 字节盐文件派生

**如果**你要把 AI-TERM 暴露到 `127.0.0.1` 以外，额外建议：前置 HTTPS 反代、明确禁用 `AI_TERM_LEGACY_OPEN`、定期轮换 token。

## 开发

```bash
./setup.sh                             # 在 venv/ 里装依赖
source venv/bin/activate
python -m pytest tests/ -q             # 跑测试
python -m py_compile $(find backend -name '*.py')   # 语法扫描
```

## 路线图

短期事项见 [TODO.md](./TODO.md)，长期议题见 GitHub Issues。当前优先方向：

- 前端 token 管理 UI
- WebSocket 首帧鉴权（把 token 移出 URL）
- 日志层敏感值脱敏
- LLM 动作代理 + 破坏性操作显式二次确认

## 参与贡献

欢迎提 Issue / Pull Request。提交代码即视为同意将该贡献以 AGPL-3.0 授权给本项目。如果商业下游授权需要签 CLA（贡献者许可协议），请联系作者。

## 开源协议

AI-TERM 采用**双重授权**：

1. **[AGPL-3.0](./LICENSE-AGPL-3.0.txt)** —— 自由使用、修改、再分发。需要遵守 AGPL 条款，特别是 § 13 中对网络部署修改版也必须公开源码的要求。
2. **[商业协议（中文）](./COMMERCIAL-LICENSE.zh-CN.md)** / **[Commercial License (English)](./COMMERCIAL-LICENSE.md)** —— 适用于闭源、专有、SaaS 等不愿意承担 AGPL 义务的场景。订单表见 [`ORDER-FORM.md`](./ORDER-FORM.md)。联系版权人获取。

按需选择。总说明见 [`LICENSE`](./LICENSE)。

## 商业合作与联系方式

商业付费使用或者寻求合作，请联系：

**📧 xxddaochang@outlook.com**

## 下一步计划 · 付费定制

下面这些方向**不在开源路线图里**，属于按需付费的定制开发：

- **服务端多用户认证模块** —— 从"单用户 loopback"升级为团队级多账号实例，独立鉴权与权限控制。
- **AI 更深度接入 Term** —— AI 直接读写 Shell、辅助排障、生成命令并一键执行。
- **Explorer ↔ Term ↔ AI 三栏联动** —— 文件上下文自动进入终端，终端输出自动喂给 AI，三者串成一条顺手的工作流。

> [!TIP]
> 这些都需要实打实的工程时间 ——「**xiaodao 也是要恰饭的** 🍚」。
> 如果你对某一项感兴趣，或者有其他需求想让我实现，欢迎邮件详聊。
> 我会按工作量报一个对等的价格，具体邮件里协商。
>
> 📧 **xxddaochang@outlook.com**

## 发布前检查清单

`git push` 到你的 fork 或镜像之前：

- [ ] 执行 `./scripts/fetch-license.sh` 把 AGPL 占位符替换为 FSF 官方文本
- [ ] 在 [`COMMERCIAL-LICENSE.md`](./COMMERCIAL-LICENSE.md) 和 [`COMMERCIAL-LICENSE.zh-CN.md`](./COMMERCIAL-LICENSE.zh-CN.md) 里填好方括号字段（许可方名称、联系方式、银行账户等）
- [ ] 特别检查《商业协议》第 16 条列出的 8 条需要律师把关的条款
- [ ] 确认 `~/.ai-term/` 或 `.cache/` 里的数据没有误入工作树
- [ ] 补上截图，替换上文里的 GitHub URL 占位符

## 致谢

站在 FastAPI、Starlette、Uvicorn、Xterm.js、ptyprocess 以及更广泛的开源生态之上构建。
