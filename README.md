<div align="center">

# AI-TERM

**An AI-augmented web terminal — file tree · shell · AI agent, side by side.**

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](./LICENSE-AGPL-3.0.txt)
[![Commercial License](https://img.shields.io/badge/license-Commercial-green.svg)](./COMMERCIAL-LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)

[English](./README.md) · [简体中文](./README.zh-CN.md)

</div>

---

## What it is

AI-TERM is a single-user, self-hosted web application that puts three
classical developer surfaces into one browser window:

- **Left panel** — a sandboxed file tree of your working directory with safe
  read/write APIs (path-traversal hardened, size-limited, symlink-aware).
- **Middle panel** — a real PTY shell over WebSocket, backed by
  `ptyprocess` on Unix and `pywinpty` on Windows.
- **Right panel** — a streaming AI assistant that talks to any
  OpenAI-compatible endpoint (DeepSeek, Qwen/DashScope, Doubao/Ark, OpenAI,
  or your own proxy).

It is designed for **local, single-user use**: one token, one browser, one
machine. Not a multi-tenant product.

## Feature highlights

- **Streaming chat (SSE)** against OpenAI-compatible APIs with per-provider
  config (apiKey, apiBase, model).
- **PTY shell** with ANSI color, Tab completion, and cursor-accurate cwd
  tracking (cross-platform: Linux `/proc/<pid>/cwd`, macOS `lsof`).
- **Access-token auth** with three fallback mechanisms (header / query /
  cookie) and a cookie auto-set on the HTML entry so browser usage is
  friction-free.
- **Rule / theme / chat persistence** on disk under `~/.cache/ai-term/`
  with strict permission hygiene (dirs 0700, files 0600).
- **Optional WebDAV sync** with AES-256-GCM + PBKDF2 encryption of credentials.
- **Plugin system** (`plugins/<name>/__init__.py`) for adding API routes at
  load time.
- **Defensive by default** — path traversal hardened, sensitive fields
  sanitized from logs, atomic writes for config, bounded async queues.

## Screenshots

_Add screenshots or a GIF here before publishing._

## Quick start

### Requirements

- Python 3.10 or newer
- macOS, Linux, or Windows 10+
- A modern browser (Chrome/Edge/Firefox/Safari)
- An API key from at least one supported provider (DeepSeek, Qwen, Doubao,
  OpenAI, or any OpenAI-compatible endpoint)

### Install

```bash
git clone https://github.com/<your-github-username>/AI-TERM.git
cd AI-TERM
./setup.sh             # creates venv + installs requirements + macOS ptyprocess fix
```

### Configure

Copy the config template and fill in one provider's API key:

```bash
mkdir -p ~/.ai-term
cp config.json.example ~/.ai-term/config.json
chmod 600 ~/.ai-term/config.json
$EDITOR ~/.ai-term/config.json   # fill in providers.<name>.apiKey
```

You can leave `access_token` empty — the server will generate one on first
start and write it back to the same file.

### Run

```bash
./run.sh
```

Open `http://127.0.0.1:8080/` in your browser. The server sets a
`HttpOnly`, `SameSite=Strict` cookie on first page load; subsequent
`fetch` and WebSocket calls authenticate automatically.

## Configuration reference

### `~/.ai-term/config.json` (user-level)

```jsonc
{
  "access_token": "auto-generated-on-first-start",
  "activeProvider": "deepseek",
  "providers": {
    "deepseek": { "apiKey": "...", "apiBase": "https://api.deepseek.com/v1", "model": "deepseek-chat" },
    "qwen":     { "apiKey": "...", "apiBase": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus" }
  },
  "sync": { "enabled": false, "url": "...", "username": "...", "password_encrypted": "..." }
}
```

See [`config.json.example`](./config.json.example) for the fully-commented template.

### `backend/app/config/ai-term.conf` (server-level)

INI file; paths support `~` expansion; see inline comments in the file.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `AI_TERM_HOST` | Uvicorn bind address | `127.0.0.1` |
| `AI_TERM_PORT` | Uvicorn port | `8080` |
| `AI_TERM_RELOAD` | Enable hot-reload (dev) | unset |
| `AI_TERM_CORS_ORIGINS` | Comma-separated origin whitelist; `*` allowed but disables credentials | localhost:8080 whitelist |
| `AI_TERM_LEGACY_OPEN` | Set to `1` to bypass token auth (emergency only) | unset |
| `AI_TERM_MASTER_PASSWORD` | Master password for WebDAV sync credential encryption | unset (derived path + random salt) |

## Project structure

```
AI-TERM/
├── backend/
│   └── app/
│       ├── api/            # HTTP route modules (files, ...)
│       ├── core/           # auth, plugin loader
│       ├── database/       # SQLite manager + schema
│       ├── services/       # agent, pty, rule, theme, sync, crypto, file, model
│       ├── static/         # CSS, JS, themes
│       ├── templates/      # Jinja2 HTML (index, popup-chat)
│       ├── utils/          # config parser
│       └── main.py         # FastAPI entry + WebSocket
├── plugins/                # drop-in Python plugins
├── docs/                   # architecture, PRD, user manual
├── tests/                  # pytest suites and verification scripts
├── setup.sh / run.sh       # macOS/Linux install + run
└── config.json.example     # user-level config template
```

## Security model

AI-TERM is **not** hardened for untrusted multi-tenant deployment. It
assumes a single trusted user on a loopback interface. Key controls:

- All HTTP APIs except `/`, `/popup-chat`, and `/static/*` require a valid
  access token (Header, Query, or Cookie).
- WebSocket upgrade validates the same token via query or cookie.
- File-service root is fixed to the launch cwd; all paths are resolved with
  `realpath` + `commonpath`; symlinks escaping the root are rejected.
- Sensitive config fields (`apiKey`, `access_token`, `password_*`) are
  stripped from any config-return endpoint.
- On-disk configs are written atomically (tmp + `os.replace`) with
  `chmod 0600`; config directories are `chmod 0700`.
- Optional WebDAV sync credentials are encrypted with AES-256-GCM; the key
  derives from an opt-in master password plus a random 16-byte salt file.

If you plan to expose AI-TERM beyond `127.0.0.1`, additionally put it
behind HTTPS + a reverse proxy and consider disabling
`AI_TERM_LEGACY_OPEN`.

## Development

```bash
./setup.sh                             # install deps in venv/
source venv/bin/activate
python -m pytest tests/ -q             # run the test suite
python -m py_compile $(find backend -name '*.py')   # syntax sweep
```

## Roadmap

See [TODO.md](./TODO.md) for short-term items and the issues tab for
longer-term ideas. High-level directions include:

- Front-end access-token management UI.
- WebSocket first-frame auth (move token out of the URL).
- Logging-layer redaction for sensitive values.
- LLM action broker with explicit user confirmation for destructive ops.

## Contributing

Pull requests and issues are welcome. By contributing, you agree that your
contribution is licensed under AGPL-3.0 to the project. If you need a
Contributor License Agreement (CLA) for commercial downstream licensing,
contact the maintainer.

## License

AI-TERM is **dual-licensed**:

1. **[AGPL-3.0](./LICENSE-AGPL-3.0.txt)** — free to use, modify, and
   distribute under AGPL terms, including the requirement to disclose
   source code of modified network-accessible deployments (AGPL § 13).
2. **[Commercial License (English)](./COMMERCIAL-LICENSE.md)** /
   **[商业协议（中文）](./COMMERCIAL-LICENSE.zh-CN.md)** — for
   proprietary, closed-source, or SaaS use where the AGPL obligations are
   inconvenient. See [`ORDER-FORM.md`](./ORDER-FORM.md) for the fillable
   order template. Contact the copyright holder to obtain.

Pick whichever suits your use case. See [`LICENSE`](./LICENSE) for the
overall dual-license notice.

## Commercial use & partnership

For commercial/paid licensing or partnership inquiries, please contact:

**📧 xxddaochang@outlook.com**

## Pre-publish checklist

Before running `git push` on a fork or mirror:

- [ ] Run `./scripts/fetch-license.sh` to replace the AGPL placeholder with
      the canonical FSF text.
- [ ] Fill in the bracketed fields (Licensor identity, contact, bank account)
      in both [`COMMERCIAL-LICENSE.md`](./COMMERCIAL-LICENSE.md) and
      [`COMMERCIAL-LICENSE.zh-CN.md`](./COMMERCIAL-LICENSE.zh-CN.md).
- [ ] Review the 8 clauses flagged in §16 of the Commercial License that
      need lawyer attention before you start selling.
- [ ] Double-check that no `~/.ai-term/` data or `.cache/` artifacts snuck
      into the working tree.
- [ ] Update screenshots and the GitHub URL placeholder above.

## Acknowledgements

Built on the shoulders of FastAPI, Starlette, Uvicorn, Xterm.js,
ptyprocess, and the broader OSS ecosystem.
