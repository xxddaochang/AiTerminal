"""
规则文件管理服务
提供规则的 CRUD 操作，基于文件系统存储 (~/.cache/ai-term/rules)
"""
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

from backend.app.database.db_manager import get_db
from backend.app.utils.config_parser import get_config


class RuleService:
    """规则管理服务 (File System Based)"""
    
    DEFAULT_RULE_CONTENT = """# AI-TERM 默认规则模板

## 系统提示词

你是一个专业的 AI 终端助手，帮助用户完成各种终端操作和编程任务。

## 核心能力

1. **命令解释**: 解释 Linux/Unix 命令的功能和参数
2. **脚本生成**: 根据需求生成 Shell、Python 等脚本
3. **问题诊断**: 分析错误日志，提供解决方案
4. **最佳实践**: 推荐安全、高效的操作方式

## 交互规范

- 使用中文回复
- 代码使用 Markdown 格式
- 危险操作需明确警告
- 提供命令执行前的说明

## 安全原则

- 不执行破坏性命令 (rm -rf /, dd, mkfs 等)
- 敏感操作需明确警告
- 保护用户隐私和数据安全
"""

    def __init__(self):
        """初始化规则服务"""
        self.config = get_config()
        
        # 获取配置
        self.storage_path = Path(os.path.expanduser(self.config.get('rules', 'storage_path', '~/.cache/ai-term/rules')))
        self.default_permission = 0o400 # Read-only for owner
        self.custom_permission = 0o600  # Read/Write for owner
        
        # 初始化数据库连接
        self.db = get_db()
        
        # 初始化存储目录和默认规则
        self._initialize()
    
    def _initialize(self):
        """初始化规则存储目录和默认规则"""
        # 创建存储目录
        self.storage_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.storage_path, 0o700)  # 仅用户可访问目录
        except Exception as e:
            print(f"Warning: Failed to chmod storage path: {e}")
        
        # 初始化 default.md
        self._ensure_default_rule()
    
    def _ensure_default_rule(self):
        """
        确保默认规则文件存在且内容正确，并同步到数据库
        - 如果不存在，创建
        - 如果内容不一致，覆盖更新
        - 设置只读权限 (chmod 400)
        - 确保数据库中有 'default' 记录
        """
        default_file = self.storage_path / 'default.md'
        
        # 计算目标内容的哈希
        target_hash = hashlib.md5(self.DEFAULT_RULE_CONTENT.encode('utf-8')).hexdigest()
        
        need_update = False
        user_modified = False

        if not default_file.exists():
            need_update = True
        else:
            # 检查内容一致性
            try:
                with open(default_file, 'r', encoding='utf-8') as f:
                    current_content = f.read()
                current_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

                if current_hash != target_hash:
                    need_update = True
                    user_modified = True
            except Exception:
                need_update = True

        # 更新文件
        if need_update:
            try:
                if user_modified:
                    # B16：默认规则被修改时不要静默覆盖，留痕并提示用户
                    backup = default_file.with_suffix(default_file.suffix + ".user.bak")
                    try:
                        import shutil
                        shutil.copy2(default_file, backup)
                        print(
                            f"[rule_service] WARNING: {default_file} 内容已被修改，"
                            f"已备份为 {backup} 后再恢复到内置默认规则。"
                            f" 若需要自定义系统提示词，请用 /api/rules 创建一个用户规则而不是改 default.md。"
                        )
                    except Exception as be:
                        print(f"[rule_service] WARNING: backup of modified default rule failed: {be}")

                if default_file.exists():
                    os.chmod(default_file, 0o600)

                with open(default_file, 'w', encoding='utf-8') as f:
                    f.write(self.DEFAULT_RULE_CONTENT)

                os.chmod(default_file, self.default_permission)

                if not user_modified:
                    print(f"已初始化默认规则: {default_file}")
            except Exception as e:
                print(f"Error initializing default rule: {e}")

        # --- 同步数据库 ---
        try:
            existing = self.db.fetchone("SELECT id FROM rules WHERE name = 'default'")
            if not existing:
                self.db.insert('rules', {
                    'name': 'default',
                    'file_path': str(default_file),
                    'description': '系统默认规则 (只读)',
                    'is_default': 1
                })
                print("Default rule inserted into DB.")
            else:
                # 确保 file_path 正确
                self.db.update('rules', {
                    'file_path': str(default_file),
                    'is_default': 1
                }, "name = 'default'")
        except Exception as e:
            print(f"Error syncing default rule to DB: {e}")

    def _validate_rule_name(self, name: str) -> bool:
        """
        验证规则名称
        只允许字母、数字、下划线和连字符
        """
        import re
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
    
    def create_rule(self, name: str, content: str, description: str = "") -> Dict[str, Any]:
        """
        创建新规则
        """
        # 验证规则名称
        if not self._validate_rule_name(name):
            raise ValueError(f"规则名称无效: {name}，只允许字母、数字、下划线和连字符")
        
        if name == 'default':
             raise ValueError("无法创建名为 'default' 的规则")

        # 文件路径
        file_path = self.storage_path / f"{name}.md"
        
        # 检查是否已存在
        if file_path.exists():
            raise ValueError(f"规则已存在: {name}")
        
        # 写入文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 设置权限
            os.chmod(file_path, self.custom_permission)
        except Exception as e:
             raise ValueError(f"创建规则文件失败: {e}")
        
        return {
            'name': name,
            'content': content,
            'description': description, # Description is not persisted in file system simple mode
            'is_default': False
        }
    
    def get_rule(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取规则内容
        """
        file_path = self.storage_path / f"{name}.md"
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                'name': name,
                'content': content,
                'description': "System Default Rule" if name == 'default' else "",
                'is_default': name == 'default'
            }
        except Exception as e:
            print(f"Error reading rule {name}: {e}")
            return None
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """
        列出所有规则
        """
        rules = []
        
        if not self.storage_path.exists():
             return []

        # 获取所有 .md 文件
        for file_path in self.storage_path.glob("*.md"):
            name = file_path.stem
            is_default = (name == 'default')
            
            # 读取部分内容作为预览 (可选)
            # content = ...
            
            rules.append({
                'name': name,
                'is_default': is_default,
                'description': "System Default Rule" if is_default else ""
            })
            
        # 排序: default 第一，其他按名称排序
        rules.sort(key=lambda x: (not x['is_default'], x['name']))
        return rules
    
    def update_rule(self, name: str, content: str, description: Optional[str] = None) -> Dict[str, Any]:
        """
        更新规则
        """
        if name == 'default':
            raise ValueError("默认规则不允许修改")
            
        file_path = self.storage_path / f"{name}.md"
        
        if not file_path.exists():
            raise ValueError(f"规则不存在: {name}")
        
        try:
            # 确保文件可写 (虽然如果是 custom_permission 应该是 600)
            if file_path.exists():
                os.chmod(file_path, 0o600)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 恢复权限
            os.chmod(file_path, self.custom_permission)
            
            return self.get_rule(name)
        except Exception as e:
            raise ValueError(f"更新规则失败: {e}")
    
    def delete_rule(self, name: str) -> bool:
        """
        删除规则
        """
        if name == 'default':
            raise ValueError("默认规则不允许删除")
            
        file_path = self.storage_path / f"{name}.md"
        
        if not file_path.exists():
             raise ValueError(f"规则不存在: {name}")
        
        try:
            os.chmod(file_path, 0o600)
            file_path.unlink()
            return True
        except Exception as e:
             raise ValueError(f"删除规则失败: {e}")
        
    def get_default_rule_content(self) -> str:
        """
        获取默认规则内容
        """
        rule = self.get_rule('default')
        return rule['content'] if rule else ""

    def get_active_rule_content(self) -> str:
        """
        获取当前激活的规则内容
        (Note: Active state is maintained by Frontend/Client for now, 
         or persisted in a user config file. This method might read from user config.)
        """
        # 为了简单起见，后端只需确保 default 存在。
        # 具体激活哪个规则，目前由前端 localStorage 决定，或者后续可以存入 config.json
        return self.get_default_rule_content()

# 全局服务实例
_rule_service_instance: Optional[RuleService] = None

def get_rule_service() -> RuleService:
    global _rule_service_instance
    if _rule_service_instance is None:
        _rule_service_instance = RuleService()
    return _rule_service_instance
