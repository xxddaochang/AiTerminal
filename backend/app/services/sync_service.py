from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json
import asyncio
from .storage_adapters import StorageAdapter
from .crypto_helper import CryptoHelper


class SyncManifest:
    """同步清单数据模型"""
    
    def __init__(self, data: dict = None):
        if data is None:
            data = self._create_empty()
        self.data = data
    
    @staticmethod
    def _create_empty() -> dict:
        """创建空清单"""
        return {
            "version": "1.2.0",
            "device_id": CryptoHelper().hash_data(CryptoHelper()._get_device_id().encode()),
            "last_sync": None,
            "items": {
                "config": None,
                "chat_sessions": [],
                "themes": [],
                "rules": []
            }
        }
    
    def to_dict(self) -> dict:
        return self.data
    
    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SyncManifest':
        return cls(json.loads(json_str))
    
    def update_timestamp(self):
        """更新同步时间戳"""
        self.data["last_sync"] = datetime.now().isoformat()


class SyncResult:
    """同步结果"""
    
    def __init__(self, success: bool = True, message: str = ""):
        self.success = success
        self.message = message
        self.pushed = 0
        self.pulled = 0
        self.failed = 0
        self.conflicts = []
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "pushed": self.pushed,
            "pulled": self.pulled,
            "failed": self.failed,
            "conflicts": self.conflicts,
            "timestamp": self.timestamp
        }


class SyncService:
    """云端同步服务"""
    
    def __init__(self, storage_adapter: StorageAdapter, encrypt_data: bool = True):
        """
        初始化同步服务
        
        Args:
            storage_adapter: 存储适配器
            encrypt_data: 是否加密数据
        """
        self.adapter = storage_adapter
        self.local_path = Path.home() / ".ai-term"
        self.crypto = CryptoHelper() if encrypt_data else None
        self.encrypt_data = encrypt_data
        
        # 确保本地目录存在
        self.local_path.mkdir(parents=True, exist_ok=True)
        (self.local_path / "chat_sessions").mkdir(exist_ok=True)
        (self.local_path / "themes").mkdir(exist_ok=True)
        (self.local_path / "rules").mkdir(exist_ok=True)
    
    async def push(self, items: List[str] = None, force: bool = False) -> SyncResult:
        """
        推送本地数据到云端
        
        Args:
            items: 要推送的项目列表,None 表示全部
            force: 是否强制覆盖云端数据
            
        Returns:
            SyncResult: 同步结果
        """
        result = SyncResult()
        
        if items is None:
            items = ["config", "chat_sessions", "themes", "rules"]
        
        try:
            for item in items:
                if item == "config":
                    success = await self._push_config()
                elif item == "chat_sessions":
                    success = await self._push_chat_sessions()
                elif item == "themes":
                    success = await self._push_themes()
                elif item == "rules":
                    success = await self._push_rules()
                else:
                    continue
                
                if success:
                    result.pushed += 1
                else:
                    result.failed += 1
            
            # 更新清单
            manifest = await self.get_local_manifest()
            manifest.update_timestamp()
            await self._upload_manifest(manifest)
            
            result.message = f"成功推送 {result.pushed} 项"
            return result
        except Exception as e:
            result.success = False
            result.message = f"推送失败: {str(e)}"
            return result
    
    async def pull(self, items: List[str] = None, force: bool = False) -> SyncResult:
        """
        从云端拉取数据到本地
        
        Args:
            items: 要拉取的项目列表,None 表示全部
            force: 是否强制覆盖本地数据
            
        Returns:
            SyncResult: 同步结果
        """
        result = SyncResult()
        
        if items is None:
            items = ["config", "chat_sessions", "themes", "rules"]
        
        try:
            not_implemented = []
            for item in items:
                if item == "config":
                    success = await self._pull_config(force)
                elif item == "chat_sessions":
                    success = await self._pull_chat_sessions(force)
                    if success is NotImplemented:
                        not_implemented.append(item); continue
                elif item == "themes":
                    success = await self._pull_themes(force)
                    if success is NotImplemented:
                        not_implemented.append(item); continue
                elif item == "rules":
                    success = await self._pull_rules(force)
                    if success is NotImplemented:
                        not_implemented.append(item); continue
                else:
                    continue

                if success:
                    result.pulled += 1
                else:
                    result.failed += 1

            msg = f"成功拉取 {result.pulled} 项"
            if not_implemented:
                msg += f"；暂未实现: {', '.join(not_implemented)}"
                # 不标失败，但如实反馈
            result.message = msg
            return result
        except Exception as e:
            result.success = False
            result.message = f"拉取失败: {str(e)}"
            return result
    
    async def sync(self) -> SyncResult:
        """
        当前实现：单向 push（本地 → 云端），仅用于首次备份或覆盖场景。

        说明：尚未实现冲突检测与智能合并；原先返回"同步完成(本地优先)"会让调用方
        误以为这是真正的双向同步。这里改为明确声明仅 push 行为，避免误导。

        Returns:
            SyncResult
        """
        result = SyncResult()

        try:
            local_manifest = await self.get_local_manifest()
            remote_manifest = await self._download_manifest()

            if remote_manifest is None:
                r = await self.push()
                r.message = (r.message or "") + "（云端无数据，执行首次 push）"
                return r

            # 注意：此处并未做冲突合并；调用者若需要更安全的行为，应显式走 push/pull。
            r = await self.push()
            r.message = (
                (r.message or "")
                + "；注意：当前 sync() 实际为单向 push，未做冲突检测与合并。"
            )
            return r
        except Exception as e:
            result.success = False
            result.message = f"同步失败: {str(e)}"
            return result
    
    async def get_local_manifest(self) -> SyncManifest:
        """生成本地数据清单"""
        manifest = SyncManifest()
        
        # 配置文件
        config_file = self.local_path / "config.json"
        if config_file.exists():
            manifest.data["items"]["config"] = {
                "hash": CryptoHelper.hash_file(str(config_file)),
                "size": config_file.stat().st_size,
                "modified": datetime.fromtimestamp(config_file.stat().st_mtime).isoformat()
            }
        
        # 聊天会话
        sessions_dir = self.local_path / "chat_sessions"
        if sessions_dir.exists():
            sessions = []
            for session_file in sessions_dir.glob("*.json"):
                sessions.append({
                    "id": session_file.stem,
                    "hash": CryptoHelper.hash_file(str(session_file)),
                    "modified": datetime.fromtimestamp(session_file.stat().st_mtime).isoformat()
                })
            manifest.data["items"]["chat_sessions"] = sessions
        
        # 主题
        themes_dir = self.local_path / "themes"
        if themes_dir.exists():
            themes = []
            for theme_file in themes_dir.glob("*.json"):
                themes.append({
                    "name": theme_file.stem,
                    "hash": CryptoHelper.hash_file(str(theme_file))
                })
            manifest.data["items"]["themes"] = themes
        
        # 规则
        rules_dir = self.local_path / "rules"
        if rules_dir.exists():
            rules = []
            for rule_file in rules_dir.glob("*.md"):
                rules.append({
                    "name": rule_file.stem,
                    "hash": CryptoHelper.hash_file(str(rule_file))
                })
            manifest.data["items"]["rules"] = rules
        
        return manifest
    
    async def get_status(self) -> dict:
        """获取同步状态"""
        manifest = await self.get_local_manifest()
        
        # 测试云端连接
        cloud_connected = await self.adapter.test_connection()
        
        return {
            "local_manifest": manifest.to_dict(),
            "cloud_connected": cloud_connected,
            "last_sync": manifest.data.get("last_sync"),
            "encrypt_enabled": self.encrypt_data
        }
    
    # ========== 私有方法 ==========
    
    async def _push_config(self) -> bool:
        """推送配置文件"""
        try:
            config_file = self.local_path / "config.json"
            if not config_file.exists():
                return True  # 无配置文件,跳过
            
            data = config_file.read_bytes()
            
            # 加密(如果启用)
            if self.encrypt_data:
                data = self.crypto.encrypt(data)
            
            return await self.adapter.upload("config.json", data)
        except Exception as e:
            print(f"Push config error: {e}")
            return False
    
    async def _push_chat_sessions(self) -> bool:
        """推送聊天会话"""
        try:
            sessions_dir = self.local_path / "chat_sessions"
            if not sessions_dir.exists():
                return True
            
            for session_file in sessions_dir.glob("*.json"):
                data = session_file.read_bytes()
                if self.encrypt_data:
                    data = self.crypto.encrypt(data)
                
                remote_path = f"chat_sessions/{session_file.name}"
                await self.adapter.upload(remote_path, data)
            
            return True
        except Exception as e:
            print(f"Push chat sessions error: {e}")
            return False
    
    async def _push_themes(self) -> bool:
        """推送自定义主题"""
        try:
            themes_dir = self.local_path / "themes"
            if not themes_dir.exists():
                return True
            
            for theme_file in themes_dir.glob("*.json"):
                data = theme_file.read_bytes()
                remote_path = f"themes/{theme_file.name}"
                await self.adapter.upload(remote_path, data)
            
            return True
        except Exception as e:
            print(f"Push themes error: {e}")
            return False
    
    async def _push_rules(self) -> bool:
        """推送自定义规则"""
        try:
            rules_dir = self.local_path / "rules"
            if not rules_dir.exists():
                return True
            
            for rule_file in rules_dir.glob("*.md"):
                data = rule_file.read_bytes()
                remote_path = f"rules/{rule_file.name}"
                await self.adapter.upload(remote_path, data)
            
            return True
        except Exception as e:
            print(f"Push rules error: {e}")
            return False
    
    async def _pull_config(self, force: bool = False) -> bool:
        """拉取配置文件"""
        try:
            data = await self.adapter.download("config.json")
            if data is None:
                return True  # 云端无数据
            
            # 解密(如果启用)
            if self.encrypt_data:
                data = self.crypto.decrypt(data)
            
            config_file = self.local_path / "config.json"
            
            # 检查冲突
            if not force and config_file.exists():
                # TODO: 实现冲突检测
                pass
            
            config_file.write_bytes(data)
            return True
        except Exception as e:
            print(f"Pull config error: {e}")
            return False
    
    async def _pull_chat_sessions(self, force: bool = False):
        """拉取聊天会话 —— 尚未实现，显式返回 NotImplemented 由上层报告。"""
        return NotImplemented

    async def _pull_themes(self, force: bool = False):
        """拉取自定义主题 —— 尚未实现。"""
        return NotImplemented

    async def _pull_rules(self, force: bool = False):
        """拉取自定义规则 —— 尚未实现。"""
        return NotImplemented
    
    async def _upload_manifest(self, manifest: SyncManifest) -> bool:
        """上传清单到云端"""
        try:
            data = manifest.to_json().encode('utf-8')
            return await self.adapter.upload("manifest.json", data)
        except Exception as e:
            print(f"Upload manifest error: {e}")
            return False
    
    async def _download_manifest(self) -> Optional[SyncManifest]:
        """从云端下载清单"""
        try:
            data = await self.adapter.download("manifest.json")
            if data is None:
                return None
            return SyncManifest.from_json(data.decode('utf-8'))
        except Exception as e:
            print(f"Download manifest error: {e}")
            return None
