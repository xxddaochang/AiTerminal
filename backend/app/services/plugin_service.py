import os
import importlib.util
import sys
import logging
from fastapi import FastAPI
from backend.app.core.plugin import Plugin

logger = logging.getLogger("uvicorn")

class PluginService:
    def __init__(self, app: FastAPI, plugin_dir: str = "plugins"):
        self.app = app
        self.plugin_dir = plugin_dir
        self.loaded_plugins = {}

    def load_plugins(self):
        """
        扫描插件目录并加载有效插件。
        """
        if not os.path.exists(self.plugin_dir):
            logger.warning(f"Plugin directory '{self.plugin_dir}' does not exist.")
            return

        for item in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, item)
            if os.path.isdir(plugin_path) and os.path.exists(os.path.join(plugin_path, "__init__.py")):
                self._load_single_plugin(item, plugin_path)

    def _load_single_plugin(self, plugin_name: str, plugin_path: str):
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(plugin_name, os.path.join(plugin_path, "__init__.py"))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[plugin_name] = module
                spec.loader.exec_module(module)

                # 期望一个名为 'Plugin' 的类或 'plugin_instance' 变量
                # 约定: __init__.py 应该暴露一个 `plugin` 实例或 `Plugin` 类
                
                if hasattr(module, "plugin") and isinstance(module.plugin, Plugin):
                    plugin_instance = module.plugin
                    plugin_instance.on_load(self.app)
                    self.loaded_plugins[plugin_name] = {
                        "instance": plugin_instance,
                        "manifest": plugin_instance.manifest,
                        "status": "active"
                    }
                    logger.info(f"Loaded plugin: {plugin_name}")
                else:
                    logger.warning(f"Plugin '{plugin_name}' does not export a valid 'plugin' instance.")
            
        except Exception as e:
            logger.error(f"Failed to load plugin '{plugin_name}': {e}")

    def get_plugins(self):
        return [
            {"id": name, "manifest": data["manifest"], "status": data["status"]}
            for name, data in self.loaded_plugins.items()
        ]
