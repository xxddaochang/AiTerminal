"""
数据库管理器
提供数据库连接、初始化和操作功能
"""
import sqlite3
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from backend.app.utils.config_parser import get_config


class DatabaseManager:
    """SQLite 数据库管理器"""
    
    def __init__(self):
        """初始化数据库管理器"""
        config = get_config()
        db_file = config.get('database', 'db_file', 'ai-term.db')
        
        # 数据库文件路径 (相对于 config 目录)
        config_dir = Path(__file__).parent.parent / 'config'
        self.db_path = config_dir / db_file
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._initialize()
    
    def _initialize(self):
        """初始化数据库表结构"""
        schema_file = Path(__file__).parent / 'schema.sql'
        
        if not schema_file.exists():
            raise FileNotFoundError(f"数据库 schema 文件不存在: {schema_file}")
        
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）
        
        Yields:
            sqlite3.Connection
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 返回字典格式
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        执行 SQL 语句
        
        Args:
            sql: SQL 语句
            params: 参数元组
            
        Returns:
            Cursor 对象
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor
    
    def fetchone(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """
        查询单条记录
        
        Args:
            sql: SQL 查询语句
            params: 参数元组
            
        Returns:
            字典格式的记录，或 None
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def fetchall(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        查询多条记录
        
        Args:
            sql: SQL 查询语句
            params: 参数元组
            
        Returns:
            字典列表
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        插入记录
        
        Args:
            table: 表名
            data: 数据字典
            
        Returns:
            插入记录的 ID
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        with self.get_connection() as conn:
            cursor = conn.execute(sql, tuple(data.values()))
            conn.commit()
            return cursor.lastrowid
    
    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = ()) -> int:
        """
        更新记录
        
        Args:
            table: 表名
            data: 更新数据字典
            where: WHERE 条件
            where_params: WHERE 参数
            
        Returns:
            影响的行数
        """
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE {where}"
        
        params = tuple(data.values()) + where_params
        
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount
    
    def delete(self, table: str, where: str, where_params: tuple = ()) -> int:
        """
        删除记录
        
        Args:
            table: 表名
            where: WHERE 条件
            where_params: WHERE 参数
            
        Returns:
            影响的行数
        """
        sql = f"DELETE FROM {table} WHERE {where}"
        
        with self.get_connection() as conn:
            cursor = conn.execute(sql, where_params)
            conn.commit()
            return cursor.rowcount


# 全局数据库实例
_db_instance: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    """
    获取全局数据库实例（单例模式）
    
    Returns:
        DatabaseManager 实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance
