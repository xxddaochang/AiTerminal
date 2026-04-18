# -*- coding: utf-8 -*-
"""
主题服务 (Theme Service)
负责管理内置主题和用户自定义主题
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Optional


class ThemeService:
    """主题管理服务"""
    
    def __init__(self, builtin_themes_dir: str = "backend/app/static/themes"):
        """
        初始化主题服务
        
        Args:
            builtin_themes_dir: 内置主题目录路径
        """
        self.builtin_dir = Path(builtin_themes_dir)
        self.custom_dir = Path.home() / ".ai-term" / "themes"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存已加载的主题
        self._theme_cache: Dict[str, dict] = {}
        self._load_all_themes()
    
    def _load_all_themes(self):
        """加载所有主题到缓存"""
        # 加载内置主题
        if self.builtin_dir.exists():
            for theme_file in self.builtin_dir.glob("*.json"):
                if theme_file.name == "theme_schema.json":
                    continue
                try:
                    with open(theme_file, 'r', encoding='utf-8') as f:
                        theme_data = json.load(f)
                        theme_data['builtin'] = True
                        self._theme_cache[theme_data['name']] = theme_data
                except Exception as e:
                    print(f"加载内置主题失败 {theme_file}: {e}")
        
        # 加载用户自定义主题
        for theme_file in self.custom_dir.glob("*.json"):
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    theme_data = json.load(f)
                    theme_data['builtin'] = False
                    self._theme_cache[theme_data['name']] = theme_data
            except Exception as e:
                print(f"加载自定义主题失败 {theme_file}: {e}")
    
    def list_themes(self) -> List[dict]:
        """
        获取所有可用主题列表
        
        Returns:
            主题列表,每个主题包含基本信息
        """
        themes = []
        for name, theme in self._theme_cache.items():
            themes.append({
                'name': theme.get('name'),
                'displayName': theme.get('displayName', name.capitalize()),
                'description': theme.get('description', ''),
                'author': theme.get('author', 'Unknown'),
                'version': theme.get('version', '1.0.0'),
                'builtin': theme.get('builtin', False)
            })
        return themes
    
    def get_theme(self, name: str) -> Optional[dict]:
        """
        获取指定主题的完整配置
        
        Args:
            name: 主题名称
            
        Returns:
            主题配置字典,如果不存在则返回 None
        """
        return self._theme_cache.get(name)
    
    def save_custom_theme(self, theme_data: dict) -> bool:
        """
        保存用户自定义主题
        
        Args:
            theme_data: 主题配置数据
            
        Returns:
            是否保存成功
        """
        try:
            # 验证必需字段
            if 'name' not in theme_data:
                raise ValueError("主题配置缺少 'name' 字段")
            if 'terminal' not in theme_data:
                raise ValueError("主题配置缺少 'terminal' 字段")
            
            name = theme_data['name']
            
            # 禁止覆盖内置主题
            existing = self._theme_cache.get(name)
            if existing and existing.get('builtin', False):
                raise ValueError(f"不能覆盖内置主题: {name}")
            
            # 保存到文件
            theme_file = self.custom_dir / f"{name}.json"
            with open(theme_file, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2, ensure_ascii=False)
            
            # 更新缓存
            theme_data['builtin'] = False
            self._theme_cache[name] = theme_data
            
            return True
        except Exception as e:
            print(f"保存自定义主题失败: {e}")
            return False
    
    def delete_custom_theme(self, name: str) -> bool:
        """
        删除用户自定义主题
        
        Args:
            name: 主题名称
            
        Returns:
            是否删除成功
        """
        try:
            theme = self._theme_cache.get(name)
            if not theme:
                raise ValueError(f"主题不存在: {name}")
            
            if theme.get('builtin', False):
                raise ValueError(f"不能删除内置主题: {name}")
            
            # 删除文件
            theme_file = self.custom_dir / f"{name}.json"
            if theme_file.exists():
                theme_file.unlink()
            
            # 从缓存中移除
            del self._theme_cache[name]
            
            return True
        except Exception as e:
            print(f"删除自定义主题失败: {e}")
            return False
    
    def validate_theme(self, theme_data: dict) -> tuple[bool, str]:
        """
        验证主题配置的合法性
        
        Args:
            theme_data: 主题配置数据
            
        Returns:
            (是否合法, 错误信息)
        """
        # 检查必需字段
        required_fields = ['name', 'terminal']
        for field in required_fields:
            if field not in theme_data:
                return False, f"缺少必需字段: {field}"
        
        # 检查终端配色必需字段
        terminal = theme_data.get('terminal', {})
        required_terminal_fields = ['background', 'foreground']
        for field in required_terminal_fields:
            if field not in terminal:
                return False, f"终端配色缺少必需字段: {field}"
        
        return True, ""
