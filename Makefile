# =============================================================================
# QuantEngine Pro - Makefile
# =============================================================================
# Cross-platform (Windows / Linux / macOS)
#
# Usage:
#   make install      - Set up dev environment
#   make test         - Run all tests
#   make backtest     - Run example backtest
#   make dashboard    - Start web dashboard
#   make docker-build - Build Docker image
#   make docker-up    - Start all services
#   make lint         - Run code linters
#   make clean        - Clean build artifacts
# =============================================================================

.PHONY: help install test backtest dashboard docker-build docker-up docker-down lint clean

# ---- Platform detection ----
ifeq ($(OS),Windows_NT)
    PYTHON := python
    VENV_PY := $(VENV)\Scripts\python
    VENV_ACTIVATE := $(VENV)\Scripts\activate
    SEP := \\
else
    PYTHON := python3
    VENV_PY := $(VENV)/bin/python
    VENV_ACTIVATE := $(VENV)/bin/activate
    SEP := /
endif

VENV := venv
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff

# ---- Colors (ANSI escape) ----
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# Development Setup
# =============================================================================

$(VENV)$(SEP)Scripts$(SEP)activate: $(VENV)$(SEP)pyvenv.cfg
$(VENV)/bin/activate: $(VENV)/pyvenv.cfg
$(VENV)/pyvenv.cfg:
	@echo "$(YELLOW)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV)
	@echo "$(GREEN)Virtual environment created$(NC)"

install: $(VENV)/pyvenv.cfg ## Install all dependencies for development
	@echo "$(YELLOW)Installing dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-asyncio pytest-cov black ruff
	@echo "$(GREEN)Installation complete!$(NC)"
	@echo "Activate: $(VENV_ACTIVATE)"

install-minimal: $(VENV)/pyvenv.cfg ## Install only core deps (no akshare, ccxt)
	@echo "$(YELLOW)Installing minimal dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install pandas numpy pyyaml loguru pydantic pyarrow fastparquet \
		plotly dash fastapi uvicorn aiohttp openai
	@echo "$(GREEN)Minimal installation complete!$(NC)"

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests
	@echo "$(YELLOW)Running tests...$(NC)"
	$(PYTEST) tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	@echo "$(YELLOW)Running tests with coverage...$(NC)"
	$(PYTEST) tests/ -v --tb=short --cov=quantengine --cov-report=html

test-smoke: ## Quick smoke test (no external deps)
	@echo "$(YELLOW)Running smoke test...$(NC)"
	$(PYTHON) tests/smoke_test.py

# =============================================================================
# Backtest
# =============================================================================

backtest: ## Run example backtest (Dual Thrust on ETH/USDT)
	@echo "$(YELLOW)Running backtest...$(NC)"
	$(PYTHON) scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT --timeframe 1h

backtest-all: ## Run all strategies
	@echo "$(YELLOW)Running all strategy backtests...$(NC)"
	for s in dual_thrust turtle bollinger dual_ma r_breaker grid_ma; do \
		echo "\n--- $$s ---"; \
		$(PYTHON) scripts/run_backtest.py --strategy $$s --symbol ETH/USDT --timeframe 1h; \
	done

# =============================================================================
# Data Download
# =============================================================================

download-crypto: ## Download crypto data (BTC, ETH)
	@echo "$(YELLOW)Downloading crypto data...$(NC)"
	$(PYTHON) scripts/download_data.py --market crypto --freq 1h

download-ashare: ## Download A-share data (top 100 stocks)
	@echo "$(YELLOW)Downloading A-share data...$(NC)"
	$(PYTHON) scripts/download_data.py --market a_share --freq 1d --max-symbols 100

# =============================================================================
# Web Dashboard
# =============================================================================

dashboard: ## Start web dashboard (http://localhost:8050)
	@echo "$(YELLOW)Starting dashboard...$(NC)"
	@echo "Dashboard: http://localhost:8050"
	@echo "API Docs:  http://localhost:8000/docs"
	$(PYTHON) -m quantengine.web.app --port 8050

api: ## Start API server only
	@echo "$(YELLOW)Starting API server...$(NC)"
	$(PYTHON) -m uvicorn quantengine.web.api:create_app --host 0.0.0.0 --port 8000

# =============================================================================
# Docker
# =============================================================================

docker-build: ## Build Docker image
	@echo "$(YELLOW)Building Docker image...$(NC)"
	docker build -t quantengine-pro:latest .

docker-up: ## Start Docker services
	@echo "$(YELLOW)Starting Docker services...$(NC)"
	docker-compose up -d

docker-up-full: ## Start all services including data downloader
	@echo "$(YELLOW)Starting full Docker stack...$(NC)"
	docker-compose --profile full up -d

docker-down: ## Stop Docker services
	@echo "$(YELLOW)Stopping Docker services...$(NC)"
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run linting (ruff)
	@echo "$(YELLOW)Linting...$(NC)"
	$(RUFF) check quantengine/ scripts/ tests/

lint-fix: ## Auto-fix linting issues
	@echo "$(YELLOW)Auto-fixing lint issues...$(NC)"
	$(RUFF) check --fix quantengine/ scripts/ tests/

format: ## Format code with black
	@echo "$(YELLOW)Formatting code...$(NC)"
	black quantengine/ scripts/ tests/

check: ## Run all checks (lint + type check)
	lint
	@echo "$(YELLOW)Type checking...$(NC)"
	mypy quantengine/ --ignore-missing-imports || true

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Clean build artifacts
	@echo "$(YELLOW)Cleaning...$(NC)"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if p.is_dir()]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*.egg-info') if p.is_dir()]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.mypy_cache'), pathlib.Path('.ruff_cache')] if p.exists()]"
	$(PYTHON) -c "[p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]"
	@echo "$(GREEN)Clean complete$(NC)"

clean-all: clean ## Clean everything including venv and data
	$(PYTHON) -c "import shutil, pathlib; shutil.rmtree('$(VENV)', ignore_errors=True)"
	$(PYTHON) -c "import shutil, pathlib; shutil.rmtree('data/parquet', ignore_errors=True); pathlib.Path('data/parquet').mkdir(parents=True, exist_ok=True)"
	$(PYTHON) -c "import pathlib; [p.unlink() for p in pathlib.Path('logs').iterdir() if p.is_file()]"
	@echo "$(GREEN)Deep clean complete$(NC)"
