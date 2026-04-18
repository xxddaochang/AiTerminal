#!/bin/bash

# 检查 venv 是否存在并激活
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "警告: 未找到虚拟环境 'venv'。依赖项可能丢失。"
    echo "建议先运行 './setup.sh'。"
fi

export PYTHONPATH=$PYTHONPATH:$(pwd):$(pwd)/backend

echo "正在启动 AI-TERM 服务器..."
# 使用 exec 将 shell 替换为 python 进程
exec python3 backend/app/main.py
