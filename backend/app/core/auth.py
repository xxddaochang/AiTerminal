from fastapi import Security, HTTPException, status, Query
from fastapi.security import APIKeyHeader, APIKeyQuery, APIKeyCookie
import os
import json
import logging
import secrets

logger = logging.getLogger("uvicorn")

# Header: X-Access-Token (推荐) / Query: ?token=... / Cookie: ai_term_token
api_key_header = APIKeyHeader(name="X-Access-Token", auto_error=False)
api_key_query = APIKeyQuery(name="token", auto_error=False)
api_key_cookie = APIKeyCookie(name="ai_term_token", auto_error=False)

# Cookie 名称(供 main.py 设置 cookie 时引用)
COOKIE_NAME = "ai_term_token"

CONFIG_PATH = os.path.expanduser("~/.ai-term/config.json")

# 逃生阀：临时恢复 v1.2.2 之前的"未配置令牌则开放访问"行为。
# 设置环境变量 AI_TERM_LEGACY_OPEN=1 即可生效（仅推荐在 127.0.0.1 本地使用）。
LEGACY_OPEN_MODE = os.environ.get("AI_TERM_LEGACY_OPEN", "").strip() in ("1", "true", "yes")

# 启动时打印一次警告，避免"静默放行"
_legacy_warned = False


def get_configured_access_token():
    """
    从 config.json 获取访问令牌。
    如果未设置，返回 None。
    """
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            token = config.get("access_token")
            # 兼容空字符串：当作未配置
            return token if token else None
    except Exception:
        return None


def ensure_access_token() -> str | None:
    """
    首次启动引导:如果 config.json 不存在或未写入 access_token,
    自动生成一个 32 字节 URL-safe token 并写入 ~/.ai-term/config.json
    (目录 chmod 700, 文件 chmod 600)。返回最终使用的 token。

    若文件 I/O 失败,返回 None(调用方可退化为 LEGACY_OPEN_MODE 或抛错)。
    """
    token = get_configured_access_token()
    if token:
        return token

    new_token = secrets.token_urlsafe(24)

    config_dir = os.path.dirname(CONFIG_PATH)
    try:
        os.makedirs(config_dir, exist_ok=True)
        try:
            os.chmod(config_dir, 0o700)
        except OSError:
            pass

        # 合并已有内容,只补 access_token 字段
        config = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    config = json.load(f) or {}
            except Exception:
                config = {}

        config["access_token"] = new_token

        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass

        logger.warning(
            f"[SECURITY] Access token auto-generated and saved to {CONFIG_PATH} "
            f"(chmod 600). 浏览器首次访问 http://127.0.0.1:<port>/ 时会自动 "
            f"通过 Cookie 认证, 无需手动输入。"
        )
        return new_token
    except Exception as e:
        logger.error(f"[SECURITY] ensure_access_token failed: {e}")
        return None


async def verify_access_token(
    header_token: str = Security(api_key_header),
    query_token: str = Security(api_key_query),
    cookie_token: str = Security(api_key_cookie),
):
    """
    验证访问令牌。
    优先级: Header > Query 参数 > Cookie。

    安全默认（v1.2.3+）：
      - 未配置 access_token 时，默认拒绝（HTTP 401），并提示配置路径。
      - 如需临时恢复旧的"未配置则开放"行为，设置环境变量 AI_TERM_LEGACY_OPEN=1。
    """
    global _legacy_warned
    expected_token = get_configured_access_token()

    if not expected_token:
        if LEGACY_OPEN_MODE:
            if not _legacy_warned:
                logger.warning(
                    "[SECURITY] AI_TERM_LEGACY_OPEN=1: access_token 未配置，已启用开放模式。"
                    " 仅建议在 127.0.0.1 本地测试使用。"
                )
                _legacy_warned = True
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Access Token not configured. 请在 ~/.ai-term/config.json 中设置 "
                "\"access_token\": \"<your-secret>\"，或在启动前临时设置环境变量 "
                "AI_TERM_LEGACY_OPEN=1 以恢复旧的开放模式（不推荐）。"
            ),
        )

    if header_token == expected_token:
        return True

    if query_token == expected_token:
        return True

    if cookie_token == expected_token:
        return True

    # 如果需要，手动检查 Authorization: Bearer <token>，但 X-Access-Token 目前更简洁。

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Access Token",
    )
