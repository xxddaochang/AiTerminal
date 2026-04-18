import os
import json
import openai
from pathlib import Path

CONFIG_DIR = Path.home() / ".ai-term"
CONFIG_FILE = CONFIG_DIR / "config.json"

class AgentService:
    def __init__(self):
        self._ensure_config()
    
    def _ensure_config(self):
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(parents=True)
        # 仅用户可读写/进入
        try:
            os.chmod(CONFIG_DIR, 0o700)
        except OSError:
            pass
        if not CONFIG_FILE.exists():
            default_config = {
                "activeProvider": "deepseek",
                "providers": {
                    "deepseek": {"apiKey": "", "baseUrl": "https://api.deepseek.com", "model": "deepseek-chat"},
                    "doubao": {"apiKey": "", "baseUrl": "https://ark.cn-beijing.volces.com/api/v3", "model": ""},
                    "qwen": {"apiKey": "", "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"}
                },
                "theme": "dark"
            }
            self._atomic_write_json(CONFIG_FILE, default_config)

    @staticmethod
    def _atomic_write_json(path, data):
        """原子写入 + 0600 权限，避免并发读到半截 json。"""
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)

    def get_config(self):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_config(self, config: dict):
        current = self.get_config()
        current.update(config)
        self._atomic_write_json(CONFIG_FILE, current)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass
    
    def _get_provider_from_model(self, model_name: str) -> str:
        """根据模型名称推断提供商。识别不出时返回 None，调用方需处理回退。"""
        if not model_name:
            return None
        lower = model_name.lower()
        # 按特征串匹配；顺序无关
        if "deepseek" in lower:
            return "deepseek"
        if "qwen" in lower or "tongyi" in lower:
            return "qwen"
        if "doubao" in lower or "ark" in lower:
            return "doubao"
        if lower.startswith("gpt-") or lower.startswith("o1-") or lower.startswith("o3-"):
            return "openai"
        if "claude" in lower:
            return "anthropic"
        if "gemini" in lower:
            return "google"
        return None

    async def stream_chat(self, messages: list, pty_service=None, override_config: dict = None):
        # ---- 解析本次会话使用的 (api_key, base_url, model) ----
        # 基准：数据库 active model。若 override_config 指定了 model：
        #   - 能识别出 provider ⇒ 用该 provider 的 DB 配置（但 api_key/base_url 仍可被 override 覆盖）
        #   - 识别不出 ⇒ 继续用当前激活模型的 api_key/base_url，只替换 model 字段
        #   （B7：之前的实现会在识别不出时回退到"激活模型 + 用户自定义模型名"但下方
        #    base_url/api_key 会再被指定 provider 覆盖，导致请求错配）
        try:
            from backend.app.services.model_service import get_model_service
            model_service = get_model_service()

            active_model = model_service.get_active_model()
            requested_model = (override_config or {}).get("model")
            target_db_model = active_model

            if requested_model:
                inferred = self._get_provider_from_model(requested_model)
                if inferred:
                    specific = model_service.get_model(inferred)
                    if specific:
                        target_db_model = specific

            if target_db_model:
                api_key = target_db_model.get("api_key", "") or ""
                base_url = target_db_model.get("base_url", "") or ""
                model = target_db_model.get("default_model", "") or ""
            else:
                # 回退到 config.json 新/旧格式
                cfg = self.get_config()
                active_provider = cfg.get("activeProvider")
                prov = (cfg.get("providers") or {}).get(active_provider) or {}
                api_key = prov.get("apiKey") or cfg.get("api_key") or ""
                base_url = prov.get("baseUrl") or cfg.get("base_url") or ""
                model = prov.get("model") or cfg.get("model") or ""

            # override 覆盖（优先级最高）
            if override_config:
                api_key = override_config.get("api_key", api_key)
                base_url = override_config.get("base_url", base_url)
                model = override_config.get("model", model)
        except Exception as e:
            print(f"Failed to load model from database: {e}, falling back to config file")
            cfg = self.get_config()
            if override_config:
                cfg = {**cfg, **override_config}
            active_provider = cfg.get("activeProvider")
            prov = (cfg.get("providers") or {}).get(active_provider) or {}
            api_key = cfg.get("api_key") or prov.get("apiKey") or ""
            base_url = cfg.get("base_url") or prov.get("baseUrl") or ""
            model = cfg.get("model") or prov.get("model") or ""



        if "deepseek" in model.lower() and "beta" in base_url:
            print("DEBUG: Using DeepSeek Beta V2 config")

        # 系统提示词
        provider_name = self._get_provider_from_model(model) or "AI"
        
        system_prompt = f"""
You are an AI Terminal Assistant (AI-TERM).
Current Model: {model} (Provider: {provider_name})

IMPORTANT: You are maintaining a conversation that may have started with a different AI model. 
Regardless of what you claimed in previous turns, you are NOW running on {model}. 
If asked "Who are you?", answer based on your CURRENT identity ({model} / {provider_name}).

You can execute commands and write files on the user's Linux system.

# Action Protocol (Strict)
To perform actions, you MUST use the following Markdown Code Blocks:

1. **Execute Shell Command**:
   Use `bash` or `sh` language.
   ```bash
   ls -la
   ```

2. **Write/Create File**:
   Use `file:<path>` language. The path is relative to Home (~).
   ```file:hello.py
   print("Hello World")
   ```

# Context
- OS: Linux
- Shell: Bash
- Current Directory: ~ (Home)

# Thinking Process
Before executing commands or writing code, briefly explain your reasoning in <thinking> tags.

Always be helpful and concise.
"""
        # 注入规则 (默认 + 激活)
        try:
            from backend.app.services.rule_service import RuleService
            rule_service = RuleService()
            
            # 1. Default Rule
            default_rule = rule_service.get_default_rule_content()
            system_prompt += f"\n\n# System Default Rule (Always Active)\n{default_rule}"
            
            # 2. Active User Rule
            active_rule = rule_service.get_active_rule_content()
            if active_rule:
                system_prompt += f"\n\n# User Active Rule (High Priority)\n{active_rule}"
                system_prompt += "\n\n# Conflict Resolution\nIf the User Active Rule conflicts with the System Default Rule, the User Active Rule takes precedence."
        except Exception as e:
            print(f"Rule Injection Error: {e}")

        # 注入系统消息 —— B8：对传入的 messages 做浅拷贝，并对要改写的最后一条再单独拷贝，
        # 避免把内部 "(System Note: ...)" 污染调用方持有的列表/字典。
        full_messages = [{"role": "system", "content": system_prompt}] + [
            dict(m) if isinstance(m, dict) else m for m in messages
        ]

        if full_messages and isinstance(full_messages[-1], dict) and full_messages[-1].get('role') == 'user':
            last = full_messages[-1]
            content = last.get('content', '')
            reminder = (
                f"\n\n(System Note: You are currently running on {model} model. "
                f"Please answer as {model}, adhering to the system prompt and ignoring "
                "any previous identity claims in the history.)"
            )
            last['content'] = (content or '') + reminder

        # 使用同步 OpenAI 客户端 (多线程) - 官方推荐方式
        import asyncio
        import threading
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        # B6：有上限的队列，避免慢消费者 + 大响应耗尽内存
        q = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()
        
        def _put(item):
            """线程安全地往有界队列里投递；满则阻塞，直到消费者消费。"""
            fut = asyncio.run_coroutine_threadsafe(q.put(item), loop)
            try:
                fut.result()
            except Exception:
                pass

        def producer():
            try:
                print(f"DEBUG: Starting stream for {model} at {base_url}", flush=True)

                stream = client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    stream=True,
                )

                print("DEBUG: Stream created successfully", flush=True)
                chunk_count = 0

                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        chunk_count += 1
                        _put(content)

                print(f"DEBUG: Stream finished, total chunks: {chunk_count}", flush=True)
                _put(None)  # EOF

            except Exception as e:
                print(f"DEBUG: Stream Error: {e}", flush=True)
                error_msg = str(e)
                try:
                    if hasattr(e, 'body') and isinstance(e.body, dict):
                        body = e.body
                        if 'message' in body:
                            error_msg = body['message']
                        elif 'error' in body:
                            if isinstance(body['error'], dict) and 'message' in body['error']:
                                error_msg = body['error']['message']
                            elif isinstance(body['error'], str):
                                error_msg = body['error']
                except Exception:
                    pass

                _put(f"Error: {error_msg}")
                _put(None)

        threading.Thread(target=producer, daemon=True).start()
        
        # Send metadata first
        meta_data = json.dumps({"meta": {"model": model, "provider": self._get_provider_from_model(model)}})
        yield f"data: {meta_data}\n\n"

        # 以 SSE 格式生成块
        while True:
            item = await q.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            if isinstance(item, str) and item.startswith("Error:"):
                 yield f"data: {json.dumps({'error': item})}\n\n"
                 break
            # 包装内容为 SSE 格式
            sse_data = json.dumps({
                "choices": [{
                    "delta": {"content": item},
                    "index": 0
                }]
            })
            yield f"data: {sse_data}\n\n"
