from abc import ABC, abstractmethod
from fastapi import FastAPI

class Plugin(ABC):
    """
    AI-TERM 插件的抽象基类。
    所有插件必须继承此类并实现必要的方法。
    """
    
    def __init__(self):
        self.manifest = {}

    @abstractmethod
    def on_load(self, app: FastAPI):
        """
        插件加载时调用。
        使用此方法注册路由、事件监听器或初始化资源。
        :param app: FastAPI 主应用程序实例。
        """
        pass

    def on_unload(self):
        """
        插件卸载时调用 (可选)。
        在此处清理资源。
        """
        pass
