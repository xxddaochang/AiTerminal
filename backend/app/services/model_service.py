"""
AI 模型配置服务
管理 AI 模型的配置信息(DeepSeek, Qwen, Doubao 等)
"""
from typing import List, Dict, Any, Optional
from backend.app.database.db_manager import get_db


class ModelService:
    """AI 模型配置服务"""
    
    def __init__(self):
        """初始化模型服务"""
        self.db = get_db()
        self.table = 'ai_modules_tab'
    
    def list_models(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """
        获取所有模型列表
        
        Args:
            active_only: 是否只返回激活的模型
            
        Returns:
            模型列表
        """
        sql = f"SELECT * FROM {self.table}"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order ASC"
        
        return self.db.fetchall(sql)
    
    def get_model(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定模型配置
        
        Args:
            provider_name: 提供商名称 (deepseek, qwen, doubao)
            
        Returns:
            模型配置字典，或 None
        """
        sql = f"SELECT * FROM {self.table} WHERE provider_name = ?"
        return self.db.fetchone(sql, (provider_name,))
    
    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """
        获取当前激活的默认模型
        
        Returns:
            激活的模型配置，或第一个可用模型
        """
        # 尝试从配置文件读取当前激活的模型
        from backend.app.utils.config_parser import get_config
        config = get_config()
        active_provider = config.get('agent', 'active_provider', 'deepseek')
        
        # 从数据库获取该模型
        model = self.get_model(active_provider)
        if model and model['is_active']:
            return model
        
        # 如果没有找到,返回第一个激活的模型
        models = self.list_models(active_only=True)
        return models[0] if models else None
    
    def save_model(self, provider_name: str, data: Dict[str, Any]) -> bool:
        """
        保存或更新模型配置
        
        Args:
            provider_name: 提供商名称
            data: 模型配置数据
            
        Returns:
            是否成功
        """
        existing = self.get_model(provider_name)
        
        # 准备数据
        update_data = {}
        allowed_fields = ['display_name', 'api_key', 'base_url', 'default_model', 
                         'available_models', 'custom_params', 'is_active', 'sort_order']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        try:
            if existing:
                # 更新现有记录
                self.db.update(self.table, update_data, "provider_name = ?", (provider_name,))
            else:
                # 插入新记录
                update_data['provider_name'] = provider_name
                self.db.insert(self.table, update_data)
            return True
        except Exception as e:
            print(f"保存模型配置失败: {e}")
            return False
    
    def activate_model(self, provider_name: str) -> bool:
        """
        激活指定模型(设置为当前使用的模型)

        同时把 provider 同步写到 config.json（activeProvider）和 ai-term.conf
        ([agent].active_provider），避免前后端/接口读到不同数据源时状态不一致（B11）。

        Args:
            provider_name: 提供商名称

        Returns:
            是否成功
        """
        model = self.get_model(provider_name)
        if not model:
            return False

        # 1) 写 ini 配置文件 ai-term.conf
        try:
            from backend.app.utils.config_parser import get_config, save_config
            config = get_config()
            config.set('agent', 'active_provider', provider_name)
            save_config(config)
        except Exception as e:
            print(f"[model_service.activate_model] update ai-term.conf failed: {e}")

        # 2) 同步 config.json 的 activeProvider 字段
        try:
            from backend.app.services.agent_service import AgentService
            AgentService().save_config({"activeProvider": provider_name})
        except Exception as e:
            print(f"[model_service.activate_model] update config.json failed: {e}")

        return True
    
    def delete_model(self, provider_name: str) -> bool:
        """
        删除模型配置
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            是否成功
        """
        # 不允许删除内置模型
        builtin_models = ['deepseek', 'qwen', 'doubao']
        if provider_name in builtin_models:
            return False
        
        try:
            self.db.delete(self.table, "provider_name = ?", (provider_name,))
            return True
        except Exception as e:
            print(f"删除模型配置失败: {e}")
            return False
    
    def validate_model_config(self, provider_name: str) -> tuple[bool, str]:
        """
        验证模型配置是否可用
        
        Args:
            provider_name: 提供商名称
            
        Returns:
            (是否可用, 错误信息)
        """
        model = self.get_model(provider_name)
        if not model:
            return False, f"模型 {provider_name} 不存在"
        
        if not model['is_active']:
            return False, f"模型 {provider_name} 未激活"
        
        if not model['api_key']:
            return False, f"模型 {provider_name} 的 API Key 未配置"
        
        if not model['base_url']:
            return False, f"模型 {provider_name} 的 Base URL 未配置"
        
        if not model['default_model']:
            return False, f"模型 {provider_name} 的默认模型未配置"
        
        return True, ""
    
    def migrate_from_config(self) -> bool:
        """
        从配置文件迁移模型配置到数据库
        
        Returns:
            是否成功
        """
        try:
            from backend.app.utils.config_parser import get_config
            config = get_config()
            
            # 检查是否有旧的配置格式
            if config.has_section('providers'):
                # 迁移 providers 配置
                for provider in ['deepseek', 'qwen', 'doubao']:
                    if config.has_option('providers', f'{provider}_api_key'):
                        data = {
                            'api_key': config.get('providers', f'{provider}_api_key', ''),
                            'base_url': config.get('providers', f'{provider}_base_url', ''),
                            'default_model': config.get('providers', f'{provider}_model', ''),
                        }
                        self.save_model(provider, data)
            
            return True
        except Exception as e:
            print(f"配置迁移失败: {e}")
            return False


# 全局服务实例
_model_service_instance: Optional[ModelService] = None


def get_model_service() -> ModelService:
    """
    获取全局模型服务实例（单例模式）
    
    Returns:
        ModelService 实例
    """
    global _model_service_instance
    if _model_service_instance is None:
        _model_service_instance = ModelService()
    return _model_service_instance
