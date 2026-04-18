"""
配置文件解析器
支持 Properties 格式，包含章节 [section] 和键值对
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigParser:
    """Properties 格式配置文件解析器"""
    
    def __init__(self, config_file: str):
        """
        初始化配置解析器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config: Dict[str, Dict[str, str]] = {}
        self._load()
    
    def _load(self):
        """加载配置文件"""
        if not self.config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_file}")
        
        current_section = "default"
        self.config[current_section] = {}
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 解析章节 [section]
                section_match = re.match(r'^\[(.+)\]$', line)
                if section_match:
                    current_section = section_match.group(1)
                    if current_section not in self.config:
                        self.config[current_section] = {}
                    continue
                
                # 解析键值对 key = value
                kv_match = re.match(r'^([^=]+)=(.*)$', line)
                if kv_match:
                    key = kv_match.group(1).strip()
                    value = kv_match.group(2).strip()
                    # 展开环境变量和 ~
                    value = self._expand_path(value)
                    self.config[current_section][key] = value
    
    def _expand_path(self, path: str) -> str:
        """
        展开路径中的 ~ 和环境变量
        
        Args:
            path: 原始路径
            
        Returns:
            展开后的路径
        """
        # 展开 ~
        if path.startswith('~'):
            path = str(Path.home()) + path[1:]
        
        # 展开环境变量 ${VAR}
        path = re.sub(r'\$\{(\w+)\}', lambda m: os.getenv(m.group(1), ''), path)
        
        return path
    
    def get(self, section: str, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取配置值
        
        Args:
            section: 章节名
            key: 键名
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        return self.config.get(section, {}).get(key, default)
    
    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """获取整数配置值"""
        value = self.get(section, key)
        if value is None:
            return default
        try:
            # 支持八进制 (如 400)
            if value.startswith('0') and len(value) > 1:
                return int(value, 8)
            return int(value)
        except ValueError:
            return default
    
    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """获取布尔配置值"""
        value = self.get(section, key)
        if value is None:
            return default
        return value.lower() in ('true', 'yes', '1', 'on')
    
    def get_section(self, section: str) -> Dict[str, str]:
        """
        获取整个章节的配置
        
        Args:
            section: 章节名
            
        Returns:
            章节配置字典
        """
        return self.config.get(section, {})
    
    def sections(self) -> list:
        """获取所有章节名"""
        return list(self.config.keys())
    
    def has_section(self, section: str) -> bool:
        """检查章节是否存在"""
        return section in self.config
    
    def has_option(self, section: str, key: str) -> bool:
        """检查配置项是否存在"""
        return section in self.config and key in self.config[section]
    
    def set(self, section: str, key: str, value: str):
        """
        设置配置值
        
        Args:
            section: 章节名
            key: 键名
            value: 值
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
    
    def save(self):
        """保存配置到文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            for section, items in self.config.items():
                if section != 'default' or items:  # Skip empty default section
                    f.write(f'[{section}]\n')
                    for key, value in items.items():
                        f.write(f'{key}={value}\n')
                    f.write('\n')
    
    def __repr__(self) -> str:
        return f"ConfigParser(file='{self.config_file}', sections={self.sections()})"


# 全局配置实例
_config_instance: Optional[ConfigParser] = None


def get_config() -> ConfigParser:
    """
    获取全局配置实例（单例模式）
    
    Returns:
        ConfigParser 实例
    """
    global _config_instance
    if _config_instance is None:
        config_path = Path(__file__).parent.parent / 'config' / 'ai-term.conf'
        _config_instance = ConfigParser(str(config_path))
    return _config_instance


def save_config(config: ConfigParser):
    """
    保存配置实例到文件
    
    Args:
        config: ConfigParser 实例
    """
    config.save()
