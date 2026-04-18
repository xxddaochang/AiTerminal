#!/bin/bash
set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}[1/3] Checking Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

USE_VENV=true
# 检查 venv 是否存在但已损坏
if [ -d "venv" ]; then
    if [ ! -f "venv/bin/activate" ]; then
        echo -e "${YELLOW}Warning: 'venv' directory exists but seems broken (missing bin/activate). Removing it...${NC}"
        rm -rf venv
    fi
fi

if [ ! -d "venv" ]; then
    echo "正在创建 Python 虚拟环境..."
    if ! python3 -m venv venv; then
        echo -e "${YELLOW}警告: 创建 venv 失败 (可能是缺少 python3-venv)。${NC}"
        echo "回退到用户级安装 (--user)..."
        USE_VENV=false
    else
        # 双重检查激活脚本是否已创建
        if [ ! -f "venv/bin/activate" ]; then
             echo -e "${YELLOW}警告: venv 已创建但缺少 activate 脚本 (系统 venv 可能已损坏)。${NC}"
             rm -rf venv
             USE_VENV=false
        fi
    fi
else
    echo "虚拟环境已存在。"
fi

echo -e "${GREEN}[2/3] Installing Dependencies...${NC}"
if [ "$USE_VENV" = "true" ]; then
    source venv/bin/activate
    pip install --upgrade pip
    if [ -f "backend/requirements.txt" ]; then
        pip install -r backend/requirements.txt
    fi
else
    # 用户级安装回退
    echo "正在安装依赖到用户目录..."
    python3 -m pip install --user --upgrade pip
    if [ -f "backend/requirements.txt" ]; then
        python3 -m pip install --user -r backend/requirements.txt
    fi
fi

# macOS 平台补装 ptyprocess
# 原因: backend/requirements.txt 里 'ptyprocess; sys_platform == "linux"' 的 PEP 508 marker
# 把 macOS 排除了,但 pty_service.py 在 macOS 上也会 import ptyprocess,必须补装。
# Windows 走 pywinpty (已在 requirements.txt 里按 marker 正确声明),这里只处理 darwin。
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}检测到 macOS,补装 ptyprocess (requirements marker 排除了该平台)...${NC}"
    if [ "$USE_VENV" = "true" ]; then
        pip install ptyprocess
    else
        python3 -m pip install --user ptyprocess
    fi
fi

echo -e "${GREEN}[3/3] 安装完成!${NC}"
if [ "$USE_VENV" = true ]; then
    echo "现在可以运行 './run.sh' 启动服务器。"
else
    echo -e "${YELLOW}注意: 依赖项已直接安装到用户主目录。${NC}"
    echo "现在可以运行 './run.sh' 启动服务器。"
fi
