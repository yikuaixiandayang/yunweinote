#!/usr/bin/env bash
# =============================================
#   运维知识库服务器 - Linux 版启动脚本
#   自动检测环境、安装依赖、构建前端、启动服务
# =============================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  运维知识库服务器 - 环境自检启动"
echo "======================================"
echo ""

# 颜色输出函数
info()  { echo -e "\033[36m[信息]\033[0m $1"; }
ok()    { echo -e "\033[32m[成功]\033[0m $1"; }
warn()  { echo -e "\033[33m[警告]\033[0m $1"; }
err()   { echo -e "\033[31m[错误]\033[0m $1"; }

VENV_DIR="$SCRIPT_DIR/_env"                    # 虚拟环境目录：app/backend/_env
FRONT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/frontend"   # 前端目录：app/frontend（与 backend 平级，不在其下）

# -------------------- Python 环境检测 --------------------
PYTHON_CMD=""

# 1. 检测本地 venv
if [ -f "$VENV_DIR/bin/python3" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python3"
    info "使用本地虚拟环境 Python"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
    info "使用本地虚拟环境 Python"
fi

# 2. 检测系统 Python
if [ -z "$PYTHON_CMD" ]; then
    if command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
        info "使用系统 Python: $(python3 --version 2>&1)"
    elif command -v python &>/dev/null; then
        PYTHON_CMD="python"
        info "使用系统 Python: $(python --version 2>&1)"
    fi
fi

# 3. 仍然没有 → 提示安装
if [ -z "$PYTHON_CMD" ]; then
    err "未检测到 Python，请先安装 Python 3.11+"
    info "Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip"
    info "CentOS/RHEL:   sudo yum install python3 python3-pip"
    info "macOS:         brew install python3"
    exit 1
fi

# -------------------- 虚拟环境 --------------------
if [ ! -f "$VENV_DIR/bin/python3" ] && [ ! -f "$VENV_DIR/bin/python" ]; then
    info "正在创建虚拟环境..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        err "虚拟环境创建失败"
        exit 1
    fi
    ok "虚拟环境创建成功"
fi

# 确定 venv 中的 Python 路径
if [ -f "$VENV_DIR/bin/python3" ]; then
    VENV_PYTHON="$VENV_DIR/bin/python3"
else
    VENV_PYTHON="$VENV_DIR/bin/python"
fi

# -------------------- 安装后端依赖 --------------------
info "检测 FastAPI..."
$VENV_PYTHON -c "import fastapi" 2>/dev/null || {
    info "正在安装后端依赖（FastAPI, Uvicorn）..."
    $VENV_PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
    if [ $? -ne 0 ]; then
        err "后端依赖安装失败"
        info "请手动运行: $VENV_PYTHON -m pip install -r $SCRIPT_DIR/requirements.txt"
        exit 1
    fi
    ok "后端依赖安装成功"
}

# -------------------- 前端构建（如已检 Node.js） --------------------
info "检测 Node.js..."
if command -v node &>/dev/null; then
    NODE_VER=$(node --version 2>&1)
    info "Node.js $NODE_VER"

    if [ ! -d "$FRONT_DIR/node_modules" ]; then
        info "安装前端依赖..."
        cd "$FRONT_DIR"
        npm install --silent 2>/dev/null || npm install
        cd "$SCRIPT_DIR"
        ok "前端依赖安装成功"
    fi

    # 检查 dist 是否存在，或 src 有更新需要重新构建
    NEED_BUILD=false
    if [ ! -d "$FRONT_DIR/dist" ]; then
        NEED_BUILD=true
    else
        # 如果 src/ 文件比 dist/ 新，也需要重构建
        SRC_NEWEST=$(find "$FRONT_DIR/src" -name "*.vue" -o -name "*.js" -o -name "*.css" | xargs -I{} stat -c %Y {} 2>/dev/null | sort -rn | head -1)
        DIST_OLDEST=$(stat -c %Y "$FRONT_DIR/dist/index.html" 2>/dev/null)
        if [ -n "$SRC_NEWEST" ] && [ -n "$DIST_OLDEST" ] && [ "$SRC_NEWEST" -gt "$DIST_OLDEST" ]; then
            NEED_BUILD=true
        fi
    fi

    if [ "$NEED_BUILD" = true ]; then
        info "构建前端..."
        cd "$FRONT_DIR"
        npm run build
        if [ $? -eq 0 ]; then
            ok "前端构建成功"
        else
            warn "前端构建失败，将使用后端直接托管模式"
        fi
        cd "$SCRIPT_DIR"
    else
        info "前端已构建，跳过"
    fi
else
    warn "未检测到 Node.js，前端构建已跳过"
    info "如需开发模式，请安装 Node.js: https://nodejs.org/"
fi

# -------------------- 启动服务器 --------------------
echo ""
echo "======================================"
echo "  环境就绪 ✓  启动 Web 服务..."
echo "  访问 http://localhost:8000 打开知识库"
echo "  按 Ctrl+C 停止服务"
echo "======================================"
echo ""

cd "$SCRIPT_DIR"                    # main.py 就在本脚本同级目录，不要再拼一层 backend
exec $VENV_PYTHON main.py
