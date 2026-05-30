#!/usr/bin/env bash
# =============================================================================
# QuantEngine Pro - Setup Script
# =============================================================================
# One-command setup for local development.
#
# Usage:
#   bash scripts/setup.sh           # Full setup (venv + all deps)
#   bash scripts/setup.sh --minimal  # Minimal setup (core deps only)
#   bash scripts/setup.sh --docker   # Docker setup only
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  QuantEngine Pro - Setup${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

MODE="${1:-full}"

# ---- Check Python ----
echo -e "${YELLOW}[1/4] Checking Python...${NC}"
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}Error: Python 3.10+ required${NC}"
    exit 1
fi
echo -e "  Using: $PYTHON ($($PYTHON --version))"

# ---- Create Virtual Environment ----
echo -e "${YELLOW}[2/4] Setting up virtual environment...${NC}"
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv 2>/dev/null || {
        echo -e "${RED}Failed to create venv. Install python3-venv:${NC}"
        echo "  sudo apt install python3-venv"
        exit 1
    }
    echo "  Virtual environment created: ./venv"
else
    echo "  Virtual environment already exists: ./venv"
fi

source venv/bin/activate
pip install --upgrade pip -q

# ---- Install Dependencies ----
echo -e "${YELLOW}[3/4] Installing dependencies...${NC}"

if [ "$MODE" == "--minimal" ]; then
    echo "  Mode: minimal (core only)"
    pip install pandas numpy pyyaml loguru pydantic pyarrow fastparquet -q
    pip install plotly dash fastapi uvicorn aiohttp openai -q
elif [ "$MODE" == "--docker" ]; then
    echo "  Mode: docker"
    echo "  Building Docker image..."
    docker build -t quantengine-pro:latest .
    echo -e "${GREEN}  Docker image built. Run: make docker-up${NC}"
    exit 0
else
    echo "  Mode: full"
    pip install -r requirements.txt -q 2>/dev/null || {
        echo -e "${YELLOW}  Some packages may have failed to install (akshare, ccxt need native deps)${NC}"
        echo "  Core packages installed. For A-share data: pip install akshare"
        echo "  For crypto data: pip install ccxt"
    }
fi

# ---- Create Directories ----
echo -e "${YELLOW}[4/4] Creating data directories...${NC}"
mkdir -p data/parquet logs
echo "  data/parquet/ (market data storage)"
echo "  logs/ (application logs)"

# ---- Verify ----
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Activate environment:"
echo -e "    ${YELLOW}source venv/bin/activate${NC}"
echo ""
echo "  Quick start:"
echo "    ${YELLOW}python scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT${NC}"
echo "    ${YELLOW}python -m quantengine.web.app --port 8050${NC}"
echo ""
echo "  Or use Makefile:"
echo "    ${YELLOW}make backtest${NC}"
echo "    ${YELLOW}make dashboard${NC}"
echo ""
echo "  Documentation: docs/ARCHITECTURE.md"
echo ""
