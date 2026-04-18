from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from pathlib import Path
import httpx
from datetime import datetime


class StorageAdapter(ABC):
    """云存储适配器抽象基类"""
    
    @abstractmethod
    async def upload(self, remote_path: str, data: bytes) -> bool:
        """
        上传数据到云端
        
        Args:
            remote_path: 云端路径
            data: 要上传的数据
            
        Returns:
            bool: 上传是否成功
        """
        pass
    
    @abstractmethod
    async def download(self, remote_path: str) -> Optional[bytes]:
        """
        从云端下载数据
        
        Args:
            remote_path: 云端路径
            
        Returns:
            Optional[bytes]: 下载的数据,失败返回 None
        """
        pass
    
    @abstractmethod
    async def list(self, prefix: str = "") -> List[str]:
        """
        列出云端文件
        
        Args:
            prefix: 路径前缀
            
        Returns:
            List[str]: 文件路径列表
        """
        pass
    
    @abstractmethod
    async def delete(self, remote_path: str) -> bool:
        """
        删除云端文件
        
        Args:
            remote_path: 云端路径
            
        Returns:
            bool: 删除是否成功
        """
        pass
    
    @abstractmethod
    async def exists(self, remote_path: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            remote_path: 云端路径
            
        Returns:
            bool: 文件是否存在
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        测试连接是否正常
        
        Returns:
            bool: 连接是否成功
        """
        pass


class WebDAVAdapter(StorageAdapter):
    """WebDAV 存储适配器"""
    
    def __init__(self, endpoint: str, username: str, password: str, base_path: str = "ai-term"):
        """
        初始化 WebDAV 适配器
        
        Args:
            endpoint: WebDAV 服务器地址
            username: 用户名
            password: 密码
            base_path: 基础路径
        """
        self.endpoint = endpoint.rstrip('/')
        self.username = username
        self.password = password
        self.base_path = base_path
        self.client = httpx.AsyncClient(
            auth=(username, password),
            timeout=30.0,
            follow_redirects=True
        )
    
    def _get_full_path(self, remote_path: str) -> str:
        """获取完整的远程路径"""
        path = f"{self.base_path}/{remote_path}".strip('/')
        return f"{self.endpoint}/{path}"
    
    async def upload(self, remote_path: str, data: bytes) -> bool:
        """上传文件到 WebDAV"""
        try:
            url = self._get_full_path(remote_path)
            
            # 确保父目录存在
            parent_dir = str(Path(remote_path).parent)
            if parent_dir != '.':
                await self._ensure_directory(parent_dir)
            
            # 上传文件
            response = await self.client.put(url, content=data)
            return response.status_code in [200, 201, 204]
        except Exception as e:
            print(f"WebDAV upload error: {e}")
            return False
    
    async def download(self, remote_path: str) -> Optional[bytes]:
        """从 WebDAV 下载文件"""
        try:
            url = self._get_full_path(remote_path)
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"WebDAV download error: {e}")
            return None
    
    async def list(self, prefix: str = "") -> List[str]:
        """列出 WebDAV 目录内容"""
        try:
            url = self._get_full_path(prefix)
            
            # PROPFIND 请求
            headers = {"Depth": "1"}
            response = await self.client.request("PROPFIND", url, headers=headers)
            
            if response.status_code != 207:  # Multi-Status
                return []
            
            # 简单解析(实际应使用 XML 解析器)
            files = []
            # TODO: 完整的 XML 解析实现
            return files
        except Exception as e:
            print(f"WebDAV list error: {e}")
            return []
    
    async def delete(self, remote_path: str) -> bool:
        """删除 WebDAV 文件"""
        try:
            url = self._get_full_path(remote_path)
            response = await self.client.delete(url)
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"WebDAV delete error: {e}")
            return False
    
    async def exists(self, remote_path: str) -> bool:
        """检查文件是否存在"""
        try:
            url = self._get_full_path(remote_path)
            response = await self.client.head(url)
            return response.status_code == 200
        except Exception:
            return False
    
    async def test_connection(self) -> bool:
        """测试 WebDAV 连接"""
        try:
            # 尝试访问根目录
            url = self._get_full_path("")
            response = await self.client.request("PROPFIND", url, headers={"Depth": "0"})
            return response.status_code in [200, 207]
        except Exception as e:
            print(f"WebDAV connection test failed: {e}")
            return False
    
    async def _ensure_directory(self, dir_path: str) -> bool:
        """确保目录存在,不存在则创建"""
        try:
            url = self._get_full_path(dir_path)
            
            # 检查是否存在
            if await self.exists(dir_path):
                return True
            
            # 创建目录
            response = await self.client.request("MKCOL", url)
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"WebDAV create directory error: {e}")
            return False
    
    async def close(self):
        """关闭连接"""
        await self.client.aclose()


class S3Adapter(StorageAdapter):
    """S3 兼容存储适配器(预留接口)"""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        # TODO: 实现 S3 客户端初始化
    
    async def upload(self, remote_path: str, data: bytes) -> bool:
        # TODO: 实现 S3 上传
        raise NotImplementedError("S3 adapter not implemented yet")
    
    async def download(self, remote_path: str) -> Optional[bytes]:
        # TODO: 实现 S3 下载
        raise NotImplementedError("S3 adapter not implemented yet")
    
    async def list(self, prefix: str = "") -> List[str]:
        # TODO: 实现 S3 列表
        raise NotImplementedError("S3 adapter not implemented yet")
    
    async def delete(self, remote_path: str) -> bool:
        # TODO: 实现 S3 删除
        raise NotImplementedError("S3 adapter not implemented yet")
    
    async def exists(self, remote_path: str) -> bool:
        # TODO: 实现 S3 存在检查
        raise NotImplementedError("S3 adapter not implemented yet")
    
    async def test_connection(self) -> bool:
        # TODO: 实现 S3 连接测试
        raise NotImplementedError("S3 adapter not implemented yet")


class CustomHTTPAdapter(StorageAdapter):
    """自定义 HTTP 服务器适配器(预留接口)"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0
        )
    
    async def upload(self, remote_path: str, data: bytes) -> bool:
        # TODO: 实现自定义 HTTP 上传
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def download(self, remote_path: str) -> Optional[bytes]:
        # TODO: 实现自定义 HTTP 下载
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def list(self, prefix: str = "") -> List[str]:
        # TODO: 实现自定义 HTTP 列表
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def delete(self, remote_path: str) -> bool:
        # TODO: 实现自定义 HTTP 删除
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def exists(self, remote_path: str) -> bool:
        # TODO: 实现自定义 HTTP 存在检查
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def test_connection(self) -> bool:
        # TODO: 实现自定义 HTTP 连接测试
        raise NotImplementedError("Custom HTTP adapter not implemented yet")
    
    async def close(self):
        """关闭连接"""
        await self.client.aclose()
