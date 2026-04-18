from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.auth import (
    verify_access_token,
    ensure_access_token,
    get_configured_access_token,
    COOKIE_NAME,
)
import os
import sys
import asyncio
import logging

logger = logging.getLogger("uvicorn")

# 启动引导: 确保存在 access_token
# (若 config.json 不存在或缺字段,自动生成并写入 ~/.ai-term/config.json)
ensure_access_token()

app = FastAPI(title="MIDS Platform (AI-TERM)", version="0.3.0")

# 配置 CORS（白名单化）
# 默认仅允许本地访问；如需开放跨源，使用环境变量 AI_TERM_CORS_ORIGINS（逗号分隔）。
# 示例：AI_TERM_CORS_ORIGINS="http://localhost:8080,http://127.0.0.1:8080"
_cors_env = os.environ.get("AI_TERM_CORS_ORIGINS", "").strip()
if _cors_env == "*":
    # 显式要求通配（不推荐）；此时必须关闭 credentials 以符合 CORS 规范
    _cors_origins = ["*"]
    _cors_credentials = False
    logger.warning("[SECURITY] CORS allow_origins=* 已启用（credentials 已自动关闭）。")
elif _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    _cors_credentials = True
else:
    _cors_origins = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

# 挂载静态文件
app.mount("/static", StaticFiles(directory="backend/app/static"), name="static")
templates = Jinja2Templates(directory="backend/app/templates")

def _attach_token_cookie(response, request: Request):
    """
    在 HTML 页面响应上设置 HttpOnly Cookie,让同源的 fetch/WebSocket 自动携带 token。
    - HttpOnly: JS 无法读取,防 XSS 偷 token
    - SameSite=Strict: 仅在同源导航/请求时发送,防 CSRF
    - Secure: 仅在 HTTPS 下启用(本地 http 开发保持关闭)
    """
    token = get_configured_access_token()
    if not token:
        return response
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=is_https,
        path="/",
        max_age=60 * 60 * 24 * 30,  # 30 天
    )
    return response


@app.get("/")
async def get_home(request: Request):
    # Starlette >=0.29 changed signature to (request, name, ...);
    # older versions accepted (name, context). Pass request as first arg
    # which works on both (context dict is optional and defaults to {"request": request}).
    resp = templates.TemplateResponse(request, "index.html")
    return _attach_token_cookie(resp, request)

@app.get("/popup-chat")
async def popup_chat(request: Request):
    """弹出聊天窗口页面"""
    resp = templates.TemplateResponse(request, "popup-chat.html")
    return _attach_token_cookie(resp, request)

# 聊天持久化 API
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException as _HTTPException  # alias to avoid late re-import

# 聊天记录存储路径
# 修正：原为 ".cache/at-term"（拼写错误），统一到项目全局使用的 "ai-term"。
# 向后兼容：若旧目录存在且新目录不存在，自动迁移一次。
CHAT_STORAGE_DIR = Path.home() / ".cache" / "ai-term" / "chats"
_LEGACY_CHAT_DIR = Path.home() / ".cache" / "at-term" / "chats"
CHAT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(CHAT_STORAGE_DIR.parent, 0o700)
except OSError:
    pass
if _LEGACY_CHAT_DIR.exists() and not any(CHAT_STORAGE_DIR.iterdir()):
    try:
        for f in _LEGACY_CHAT_DIR.glob("session-*.json"):
            f.rename(CHAT_STORAGE_DIR / f.name)
    except Exception:
        pass  # 迁移失败不影响主功能

# 仅允许字母/数字/下划线/连字符/点，防止 /api/chat/load?session=... 路径遍历
_SESSION_NAME_RE = re.compile(r"^session-[0-9A-Za-z_.\-]+\.json$")


def _safe_session_path(filename: str) -> Path:
    """校验并返回 session 文件的安全路径；失败时抛 HTTPException。"""
    if not _SESSION_NAME_RE.match(filename):
        raise _HTTPException(status_code=400, detail="Invalid session filename")
    p = (CHAT_STORAGE_DIR / filename).resolve()
    if p.parent != CHAT_STORAGE_DIR.resolve():
        raise _HTTPException(status_code=400, detail="Invalid session path")
    return p


@app.post("/api/chat/save", dependencies=[Depends(verify_access_token)])
async def save_chat(request: Request):
    """保存聊天记录。

    返回 filename 方便前端后续用 /api/chat/load?session=<filename> 精确回放。
    修复 B2：文件名加 uuid 短前缀，避免同秒内多次保存相互覆盖。
    """
    data = await request.json()
    chat_history = data.get("chatHistory", [])
    if not isinstance(chat_history, list):
        raise _HTTPException(status_code=400, detail="chatHistory must be a list")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    filename = f"session-{timestamp}-{suffix}.json"
    filepath = CHAT_STORAGE_DIR / filename

    # 原子写入，避免并发读到半截
    tmp = str(filepath) + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, filepath)

    return {
        "success": True,
        "filename": filename,
        "filepath": str(filepath),
    }


@app.get("/api/chat/load", dependencies=[Depends(verify_access_token)])
async def load_chat(session: str | None = None):
    """加载聊天记录。

    - 不传 session：返回最新一次会话（保留旧行为）。
    - 传 session=<filename>：精确加载该会话（B3）。
    """
    if not CHAT_STORAGE_DIR.exists():
        return {"chatHistory": []}

    if session:
        target = _safe_session_path(session)
        if not target.is_file():
            raise _HTTPException(status_code=404, detail=f"Session not found: {session}")
        with open(target, 'r', encoding='utf-8') as f:
            chat_history = json.load(f)
        return {
            "chatHistory": chat_history,
            "filename": target.name,
            "filepath": str(target),
        }

    session_files = sorted(CHAT_STORAGE_DIR.glob("session-*.json"), reverse=True)
    if not session_files:
        return {"chatHistory": []}

    latest_file = session_files[0]
    with open(latest_file, 'r', encoding='utf-8') as f:
        chat_history = json.load(f)
    return {
        "chatHistory": chat_history,
        "filename": latest_file.name,
        "filepath": str(latest_file),
    }


@app.get("/api/chat/list", dependencies=[Depends(verify_access_token)])
async def list_chats():
    """列出所有聊天会话"""
    if not CHAT_STORAGE_DIR.exists():
        return {"sessions": []}

    sessions = []
    for filepath in sorted(CHAT_STORAGE_DIR.glob("session-*.json"), reverse=True):
        sessions.append({
            "filename": filepath.name,
            "filepath": str(filepath),
            "timestamp": filepath.stat().st_mtime,
        })

    return {"sessions": sessions}


from backend.app.services.pty_service import PTYService
from backend.app.api import files

from pydantic import BaseModel

from fastapi.responses import StreamingResponse
from backend.app.services.agent_service import AgentService

# 代理服务
# 代理服务
agent_service = AgentService()

# 全局 PTY 引用 (多用户/标签页模式)
active_ptys: dict[str, PTYService] = {}

class ProviderConfig(BaseModel):
    apiKey: str | None = ""
    baseUrl: str | None = ""
    model: str | None = ""

class ConfigRequest(BaseModel):
    activeProvider: str | None = "deepseek"
    providers: dict[str, ProviderConfig] | None = None
    theme: str | None = "dark"
    # 保留旧字段以兼容旧版本，主要数据源是 providers
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None

class ChatRequest(BaseModel):
    messages: list
    session_id: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None

_SENSITIVE_KEYS = {"api_key", "apiKey", "access_token", "password", "secret"}


def _mask_sensitive(value):
    """对敏感字段做脱敏显示（保留前 2 / 后 2 字符，中间 ***）。"""
    if not isinstance(value, str) or not value:
        return value
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _sanitize_config(cfg):
    """递归脱敏配置中的敏感字段，不修改原对象。"""
    if isinstance(cfg, dict):
        return {
            k: (_mask_sensitive(v) if k in _SENSITIVE_KEYS else _sanitize_config(v))
            for k, v in cfg.items()
        }
    if isinstance(cfg, list):
        return [_sanitize_config(v) for v in cfg]
    return cfg


@app.get("/api/agent/config", dependencies=[Depends(verify_access_token)])
async def get_config():
    """获取配置（敏感字段已脱敏）。"""
    return _sanitize_config(agent_service.get_config())


@app.post("/api/agent/config", dependencies=[Depends(verify_access_token)])
async def update_config(config: ConfigRequest):
    agent_service.save_config(config.model_dump(exclude_unset=True))
    return {"status": "ok"}

def _resolve_active_api_key(req_overrides: "ChatRequest") -> tuple[bool, str]:
    """
    解析当前会话将使用的 api_key，返回 (是否可用, 说明)。
    数据源优先级与 AgentService.stream_chat 保持一致：
      1. 请求体 api_key 覆盖
      2. 数据库 model_service 中激活的模型
      3. config.json 的 providers[activeProvider].apiKey
      4. 旧字段 config["api_key"]（向后兼容）
    """
    if getattr(req_overrides, "api_key", None):
        return True, "override"

    # 2) 数据库
    try:
        from backend.app.services.model_service import get_model_service
        db_model = get_model_service().get_active_model()
        if db_model and db_model.get("api_key"):
            return True, "db"
    except Exception:
        pass

    # 3) config.json 新格式 providers[activeProvider].apiKey
    try:
        cfg = agent_service.get_config()
        active = cfg.get("activeProvider")
        if active:
            providers = cfg.get("providers") or {}
            prov = providers.get(active) or {}
            if prov.get("apiKey"):
                return True, "config.providers"
        # 4) 旧平铺字段
        if cfg.get("api_key"):
            return True, "config.legacy"
    except Exception:
        pass

    return False, "missing"


@app.post("/api/agent/chat", dependencies=[Depends(verify_access_token)])
async def chat_agent(req: ChatRequest):
    # 流式传输前验证 API Key（已兼容数据库、providers 新格式、旧平铺字段）
    ok, source = _resolve_active_api_key(req)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=(
                "API Key not configured. 请在设置中为当前激活的提供商填入 API Key，"
                "或在请求里以 api_key 字段覆盖。"
            ),
        )

    
    # 获取 PTY 上下文
    pty = None
    if req.session_id and req.session_id in active_ptys:
        pty = active_ptys[req.session_id]
    elif active_ptys:
         # 如果未指定，默认为第一个 (回退策略)
        pty = next(iter(active_ptys.values()))

    # 创建覆盖配置
    override_config = {}
    if req.model:
        override_config["model"] = req.model
    if req.api_key:
        override_config["api_key"] = req.api_key
    if req.base_url:
        override_config["base_url"] = req.base_url

    print(f"DEBUG: Internal Chat Request - Session: {req.session_id}")
    print(f"DEBUG: Req Model: {req.model}, Req BaseURL: {req.base_url}")
    print(f"DEBUG: Override Config: {override_config}")

    return StreamingResponse(agent_service.stream_chat(req.messages, pty_service=pty, override_config=override_config), media_type="text/event-stream")

# Rules API (v2.0 - Database-backed)
from backend.app.services.rule_service import get_rule_service
from fastapi import HTTPException

rule_service = get_rule_service()

class RuleCreateRequest(BaseModel):
    name: str
    content: str
    description: str = ""

class RuleUpdateRequest(BaseModel):
    content: str
    description: str | None = None

@app.get("/api/rules")
async def list_rules():
    """列出所有规则"""
    return rule_service.list_rules()

@app.get("/api/rules/{name}")
async def get_rule(name: str):
    """获取规则内容"""
    rule = rule_service.get_rule(name)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"规则不存在: {name}")
    return rule

@app.post("/api/rules", dependencies=[Depends(verify_access_token)])
async def create_rule(req: RuleCreateRequest):
    """创建新规则"""
    try:
        result = rule_service.create_rule(req.name, req.content, req.description)
        return {"status": "ok", "rule": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/rules/{name}", dependencies=[Depends(verify_access_token)])
async def update_rule(name: str, req: RuleUpdateRequest):
    """更新规则"""
    try:
        result = rule_service.update_rule(name, req.content, req.description)
        return {"status": "ok", "rule": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/rules/{name}", dependencies=[Depends(verify_access_token)])
async def delete_rule(name: str):
    """删除规则"""
    try:
        rule_service.delete_rule(name)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# 插件服务
from backend.app.services.plugin_service import PluginService
plugin_service = PluginService(app, plugin_dir="plugins")
plugin_service.load_plugins()

@app.get("/api/plugins", tags=["Plugins"], dependencies=[Depends(verify_access_token)])
async def list_plugins():
    return plugin_service.get_plugins()

# 主题服务
from backend.app.services.theme_service import ThemeService
theme_service = ThemeService()

@app.get("/api/themes", tags=["Themes"])
async def list_themes():
    """获取所有可用主题列表"""
    return theme_service.list_themes()

@app.get("/api/themes/{name}", tags=["Themes"])
async def get_theme(name: str):
    """获取指定主题的完整配置"""
    theme = theme_service.get_theme(name)
    if not theme:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"主题不存在: {name}")
    return theme

class ThemeRequest(BaseModel):
    theme_data: dict

@app.post("/api/themes/custom", tags=["Themes"], dependencies=[Depends(verify_access_token)])
async def save_custom_theme(req: ThemeRequest):
    """保存用户自定义主题"""
    # 验证主题配置
    is_valid, error_msg = theme_service.validate_theme(req.theme_data)
    if not is_valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 保存主题
    success = theme_service.save_custom_theme(req.theme_data)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="保存主题失败")
    
    return {"status": "ok", "message": "主题保存成功"}

@app.delete("/api/themes/custom/{name}", tags=["Themes"], dependencies=[Depends(verify_access_token)])
async def delete_custom_theme(name: str):
    """删除用户自定义主题"""
    success = theme_service.delete_custom_theme(name)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="删除主题失败")
    return {"status": "ok", "message": "主题删除成功"}

@app.get("/api/themes/export/{name}", tags=["Themes"])
async def export_theme(name: str):
    """导出主题为 JSON 文件"""
    theme = theme_service.get_theme(name)
    if not theme:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"主题不存在: {name}")
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content=theme,
        headers={
            "Content-Disposition": f"attachment; filename={name}.json"
        }
    )

# 模型服务 (AI 模型配置管理)
from backend.app.services.model_service import get_model_service
from fastapi import HTTPException

model_service = get_model_service()

class ModelConfigRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    is_active: bool | None = None

@app.get("/api/models", tags=["Models"])
async def list_models():
    """获取所有 AI 模型列表"""
    try:
        models = model_service.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")

# 注意：静态路径 /api/models/active/current 必须定义在 /api/models/{provider_name}
# 之前，避免日后扩展为同深度时被参数路径吞掉（B18）。
@app.get("/api/models/active/current", tags=["Models"])
async def get_active_model():
    """获取当前激活的模型"""
    model = model_service.get_active_model()
    if not model:
        raise HTTPException(status_code=404, detail="没有激活的模型")
    return model


@app.get("/api/models/{provider_name}", tags=["Models"])
async def get_model(provider_name: str):
    """获取指定模型配置"""
    # 'active' 是保留字，避免与 /api/models/active/current 混淆
    if provider_name == "active":
        raise HTTPException(status_code=400, detail="'active' is reserved; use /api/models/active/current")
    model = model_service.get_model(provider_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"模型不存在: {provider_name}")
    return model

@app.post("/api/models/{provider_name}", tags=["Models"], dependencies=[Depends(verify_access_token)])
async def save_model(provider_name: str, req: ModelConfigRequest):
    """保存或更新模型配置"""
    try:
        data = req.model_dump(exclude_unset=True)
        success = model_service.save_model(provider_name, data)
        if not success:
            raise HTTPException(status_code=500, detail="保存模型配置失败")
        return {"status": "ok", "message": "模型配置已保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")

@app.put("/api/models/{provider_name}/activate", tags=["Models"], dependencies=[Depends(verify_access_token)])
async def activate_model(provider_name: str):
    """激活指定模型"""
    # 检查模型是否存在
    model = model_service.get_model(provider_name)
    if not model:
        raise HTTPException(status_code=404, detail=f"模型 {provider_name} 不存在")
    
    # 检查基本配置（不检查 is_active，因为我们正在激活它）
    if not model['api_key']:
        raise HTTPException(status_code=400, detail=f"模型 {provider_name} 的 API Key 未配置")
    if not model['base_url']:
        raise HTTPException(status_code=400, detail=f"模型 {provider_name} 的 Base URL 未配置")
    if not model['default_model']:
        raise HTTPException(status_code=400, detail=f"模型 {provider_name} 的默认模型未配置")
    
    success = model_service.activate_model(provider_name)
    if not success:
        raise HTTPException(status_code=500, detail="激活模型失败")
    
    return {"status": "ok", "message": f"模型 {provider_name} 已激活"}

@app.delete("/api/models/{provider_name}", tags=["Models"], dependencies=[Depends(verify_access_token)])
async def delete_model(provider_name: str):
    """删除模型配置"""
    success = model_service.delete_model(provider_name)
    if not success:
        raise HTTPException(status_code=400, detail="无法删除内置模型或删除失败")
    return {"status": "ok", "message": "模型已删除"}

# 同步服务
from backend.app.services.sync_service import SyncService
from backend.app.services.storage_adapters import WebDAVAdapter
# BaseModel 已在文件顶部导入，这里不重复 import

class SyncConfigRequest(BaseModel):
    enabled: bool
    provider: str  # webdav, s3, custom
    endpoint: str
    username: str
    password: str
    auto_sync: bool = True
    sync_interval: int = 300
    items: list[str] = ["config", "chat_sessions", "themes", "rules"]
    encrypt_data: bool = True

class SyncPushRequest(BaseModel):
    items: list[str] = None
    force: bool = False

# 全局同步服务实例(延迟初始化)
sync_service_instance = None

def get_sync_service() -> SyncService:
    """获取同步服务实例"""
    global sync_service_instance
    if sync_service_instance is None:
        # 从配置文件加载同步配置
        import json
        from pathlib import Path
        config_file = Path.home() / ".ai-term" / "sync_config.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                sync_config = json.load(f)
                if sync_config.get("enabled"):
                    # 创建存储适配器
                    if sync_config["provider"] == "webdav":
                        adapter = WebDAVAdapter(
                            endpoint=sync_config["endpoint"],
                            username=sync_config["username"],
                            password=sync_config["password"]
                        )
                        sync_service_instance = SyncService(
                            storage_adapter=adapter,
                            encrypt_data=sync_config.get("encrypt_data", True)
                        )
    return sync_service_instance

@app.get("/api/sync/config", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def get_sync_config():
    """获取同步配置"""
    import json
    from pathlib import Path
    config_file = Path.home() / ".ai-term" / "sync_config.json"
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
            # 隐藏密码
            if "password" in config:
                config["password"] = "***"
            return config
    return {"enabled": False}

@app.post("/api/sync/config", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def save_sync_config(req: SyncConfigRequest):
    """保存同步配置"""
    import json
    from pathlib import Path
    
    config_dir = Path.home() / ".ai-term"
    config_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(config_dir, 0o700)
    except OSError:
        pass
    config_file = config_dir / "sync_config.json"

    # 保存配置（原子写入 + 0600）
    config_data = req.model_dump()
    tmp_file = str(config_file) + ".tmp"
    with open(tmp_file, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(tmp_file, 0o600)
    except OSError:
        pass
    os.replace(tmp_file, config_file)
    
    # 重新初始化同步服务
    global sync_service_instance
    sync_service_instance = None
    
    # 测试连接
    service = get_sync_service()
    if service:
        connected = await service.adapter.test_connection()
        return {"status": "ok", "message": "配置已保存", "connected": connected}
    
    return {"status": "ok", "message": "配置已保存"}

@app.post("/api/sync/push", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def sync_push(req: SyncPushRequest):
    """推送数据到云端"""
    service = get_sync_service()
    if not service:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="同步服务未配置")
    
    result = await service.push(items=req.items, force=req.force)
    return result.to_dict()

@app.post("/api/sync/pull", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def sync_pull(req: SyncPushRequest):
    """从云端拉取数据"""
    service = get_sync_service()
    if not service:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="同步服务未配置")
    
    result = await service.pull(items=req.items, force=req.force)
    return result.to_dict()

@app.post("/api/sync/sync", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def sync_bidirectional():
    """智能双向同步"""
    service = get_sync_service()
    if not service:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="同步服务未配置")
    
    result = await service.sync()
    return result.to_dict()

@app.get("/api/sync/status", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def get_sync_status():
    """获取同步状态"""
    service = get_sync_service()
    if not service:
        return {"enabled": False, "cloud_connected": False}
    
    status = await service.get_status()
    return status

@app.get("/api/sync/manifest", tags=["Sync"], dependencies=[Depends(verify_access_token)])
async def get_sync_manifest():
    """获取本地数据清单"""
    service = get_sync_service()
    if not service:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="同步服务未配置")
    
    manifest = await service.get_local_manifest()
    return manifest.to_dict()

# 包含路由
app.include_router(files.router, prefix="/api/fs", tags=["FileSystem"], dependencies=[Depends(verify_access_token)])

@app.websocket("/ws/terminal/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, token: str | None = None):
    # 验证 WebSocket Token
    # 支持三种来源: ?token=... 查询串 / Cookie: ai_term_token / (未配置时视环境变量)
    from backend.app.core.auth import get_configured_access_token, COOKIE_NAME, LEGACY_OPEN_MODE
    expected = get_configured_access_token()
    if expected:
        cookie_token = websocket.cookies.get(COOKIE_NAME)
        if token != expected and cookie_token != expected:
            await websocket.close(code=1008) # 策略违规
            return
    else:
        # 未配置 token: 与 HTTP 保持一致的默认拒绝(除非启用 LEGACY_OPEN_MODE)
        if not LEGACY_OPEN_MODE:
            await websocket.close(code=1008)
            return

    await websocket.accept()
    
    # 创建或获取 PTY (每个标签页一个 PTY)
    pty = PTYService()
    pty.start()
    active_ptys[client_id] = pty
    
    # 任务：从 PTY 读取并发送到 WS
    async def send_output():
        async for data in pty.read_generator():
            try:
                await websocket.send_text(data)
            except:
                break
    
    output_task = asyncio.create_task(send_output())

    _TOCHAT_PREFIX = ":toChat "

    def _strip_tochat(cmd: str) -> str:
        # 用 removeprefix 代替硬编码切片 8
        return cmd.removeprefix(_TOCHAT_PREFIX).lstrip()

    try:
        while True:
            data = await websocket.receive_text()

            # JSON 协议 (调整大小和命令)
            if data.startswith('{'):
                import json as _json
                try:
                    msg = _json.loads(data)
                except Exception as parse_err:
                    # 协议错误不要静默吞
                    logger.warning("WS JSON parse error: %s; payload=%r", parse_err, data[:200])
                    continue

                try:
                    # 调整大小
                    if 'cols' in msg:
                        pty.resize(int(msg.get('cols', 80)), int(msg.get('rows', 24)))
                        continue

                    # 命令 (v2.5)
                    if msg.get('type') == 'cmd':
                        cmd = (msg.get('data') or '').strip()
                        if cmd.startswith(_TOCHAT_PREFIX):
                            content = _strip_tochat(cmd)
                            await websocket.send_text(_json.dumps({
                                "type": "system",
                                "action": "chat",
                                "content": content,
                            }))
                        elif cmd == ':clear':
                            pty.write('clear\n')
                        continue
                except Exception as e:
                    logger.warning("WS handler error: %s", e)
                    continue

            # 原始文本命令处理 (粘贴/运行)
            if data.startswith(':'):
                import json as _json
                cmd = data.strip()
                if cmd.startswith(_TOCHAT_PREFIX):
                    content = _strip_tochat(cmd)
                    await websocket.send_text(_json.dumps({
                        "type": "system",
                        "action": "chat",
                        "content": content,
                    }))
                    continue
                if cmd == ':clear':
                    pty.write('clear\n')
                    continue

            # 将原始数据写入 PTY
            pty.write(data)

    except Exception as e:
        logger.warning("WS 错误: %s", e)
    finally:
        output_task.cancel()
        # 等一下读任务真正结束，避免留下悬挂 future
        try:
            await asyncio.wait_for(output_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
        pty.stop()
        if client_id in active_ptys:
            del active_ptys[client_id]

if __name__ == "__main__":
    import uvicorn
    # 安全默认：仅本机回环地址。
    # 需要对外提供服务时，显式设置 AI_TERM_HOST=0.0.0.0（并务必先配置 access_token）。
    _host = os.environ.get("AI_TERM_HOST", "127.0.0.1")
    _port = int(os.environ.get("AI_TERM_PORT", "8080"))
    _reload = os.environ.get("AI_TERM_RELOAD", "").strip() in ("1", "true", "yes")
    if _host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "[SECURITY] 正在监听非本地地址 %s，请确保已配置 access_token 并限制 CORS。",
            _host,
        )
    # 注意：使用完整模块路径 backend.app.main:app（以项目根为 CWD 启动）。
    uvicorn.run("backend.app.main:app", host=_host, port=_port, reload=_reload)
