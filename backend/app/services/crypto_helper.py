from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("uvicorn")

# 旧版本（<= v1.2.2）写入云端的数据使用的就是这个固定盐；
# 为保持向后兼容，解密路径仍默认使用它；加密路径根据选项可切换到随机盐。
_LEGACY_FIXED_SALT = b'ai-term-sync-salt-v1'

# 已打印过"使用固定盐"警告的标记，避免每次构造都刷日志
_fixed_salt_warned = False


class CryptoHelper:
    """数据加密辅助类 - AES-256-GCM

    密钥派生优先级（由高到低）：
      1. 显式传入的 master_password 参数
      2. 环境变量 AI_TERM_MASTER_PASSWORD
      3. 设备唯一标识（/etc/machine-id 等） —— 同机任意进程可重建，安全性较弱
    盐优先级：
      1. 显式传入的 salt 参数
      2. salt_file 指定的文件里保存的随机盐（首次使用时自动生成 16 字节并 chmod 600）
      3. _LEGACY_FIXED_SALT（向后兼容已有加密数据）
    """

    def __init__(
        self,
        master_password: Optional[str] = None,
        *,
        salt: Optional[bytes] = None,
        salt_file: Optional[str] = None,
    ):
        # ----- 密码来源 -----
        if master_password is None:
            master_password = os.environ.get("AI_TERM_MASTER_PASSWORD") or None

        if master_password:
            password_str = master_password
            _password_source = "master_password"
        else:
            password_str = self._get_device_id()
            _password_source = "device_id"
            logger.info(
                "[CRYPTO] 未提供主密码，回退到设备 ID 派生密钥。"
                " 同机其他进程可推导同一密钥；如需更强隔离，请设置 AI_TERM_MASTER_PASSWORD。"
            )

        # ----- 盐来源 -----
        if salt is None and salt_file:
            salt = self._load_or_create_salt_file(salt_file)

        if salt is None:
            global _fixed_salt_warned
            if not _fixed_salt_warned:
                logger.warning(
                    "[CRYPTO] 使用内置固定盐（向后兼容旧数据）。"
                    " 如需更强安全，请传入 salt_file=\"...\" 让程序生成每用户随机盐。"
                )
                _fixed_salt_warned = True
            salt = _LEGACY_FIXED_SALT

        self._salt = salt
        self._password_source = _password_source
        self.key = self._derive_key_from_password(password_str, salt)

    @staticmethod
    def _load_or_create_salt_file(path: str) -> bytes:
        """从 salt_file 读取 16 字节盐；不存在则生成一个并以 0600 保存。"""
        p = Path(os.path.expanduser(path))
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p.parent, 0o700)
        except OSError:
            pass
        if p.exists():
            data = p.read_bytes()
            if len(data) >= 16:
                return data[:16]
            logger.warning("[CRYPTO] salt_file %s 内容异常（长度 %d），重新生成。", p, len(data))
        new_salt = get_random_bytes(16)
        # 原子写 + 0600
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(new_salt)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, p)
        return new_salt
    
    def _get_device_id(self) -> str:
        """获取设备唯一标识"""
        try:
            # Linux: 使用 machine-id
            if os.path.exists('/etc/machine-id'):
                with open('/etc/machine-id', 'r') as f:
                    return f.read().strip()
            # macOS: 使用硬件 UUID
            elif os.path.exists('/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist'):
                import subprocess
                result = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'], 
                                       capture_output=True, text=True)
                # 简化处理,实际应解析 plist
                return hashlib.sha256(result.stdout.encode()).hexdigest()
            else:
                # 回退方案:使用用户名 + 主机名
                import socket
                import getpass
                fallback = f"{getpass.getuser()}@{socket.gethostname()}"
                return hashlib.sha256(fallback.encode()).hexdigest()
        except Exception:
            # 最终回退
            return "ai-term-default-device-id"
    
    def _derive_key_from_password(self, password: str, salt: bytes = None) -> bytes:
        """
        从密码派生 256 位密钥
        
        Args:
            password: 密码字符串
            salt: 盐值,如果为 None 则使用固定盐(不推荐,但简化实现)
            
        Returns:
            bytes: 32 字节密钥
        """
        if salt is None:
            # 使用固定盐(生产环境应存储随机盐)
            salt = b'ai-term-sync-salt-v1'
        
        # PBKDF2 派生密钥
        key = PBKDF2(
            password.encode('utf-8'),
            salt,
            dkLen=32,  # 256 bits
            count=100000,  # 迭代次数
            hmac_hash_module=hashlib.sha256
        )
        return key
    
    def encrypt(self, data: bytes) -> bytes:
        """
        使用 AES-256-GCM 加密数据
        
        Args:
            data: 要加密的数据
            
        Returns:
            bytes: 加密后的数据 (nonce + tag + ciphertext)
        """
        try:
            # 创建 AES-GCM 密码器
            cipher = AES.new(self.key, AES.MODE_GCM)
            
            # 加密并生成认证标签
            ciphertext, tag = cipher.encrypt_and_digest(data)
            
            # 组合: nonce(16) + tag(16) + ciphertext
            return cipher.nonce + tag + ciphertext
        except Exception as e:
            raise RuntimeError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        使用 AES-256-GCM 解密数据
        
        Args:
            encrypted_data: 加密的数据 (nonce + tag + ciphertext)
            
        Returns:
            bytes: 解密后的数据
        """
        try:
            # 提取组件
            nonce = encrypted_data[:16]
            tag = encrypted_data[16:32]
            ciphertext = encrypted_data[32:]
            
            # 创建密码器并解密
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            return plaintext
        except Exception as e:
            raise RuntimeError(f"Decryption failed: {e}")
    
    def encrypt_string(self, text: str) -> str:
        """
        加密字符串并返回 Base64 编码
        
        Args:
            text: 要加密的字符串
            
        Returns:
            str: Base64 编码的加密数据
        """
        import base64
        encrypted = self.encrypt(text.encode('utf-8'))
        return base64.b64encode(encrypted).decode('ascii')
    
    def decrypt_string(self, encrypted_text: str) -> str:
        """
        解密 Base64 编码的加密字符串
        
        Args:
            encrypted_text: Base64 编码的加密数据
            
        Returns:
            str: 解密后的字符串
        """
        import base64
        encrypted = base64.b64decode(encrypted_text.encode('ascii'))
        decrypted = self.decrypt(encrypted)
        return decrypted.decode('utf-8')
    
    @staticmethod
    def hash_file(file_path: str) -> str:
        """
        计算文件的 SHA-256 哈希值
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 十六进制哈希值
        """
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            raise RuntimeError(f"Failed to hash file {file_path}: {e}")
    
    @staticmethod
    def hash_data(data: bytes) -> str:
        """
        计算数据的 SHA-256 哈希值
        
        Args:
            data: 数据
            
        Returns:
            str: 十六进制哈希值
        """
        return hashlib.sha256(data).hexdigest()
