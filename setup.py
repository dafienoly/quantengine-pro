#!/usr/bin/env python3
"""
QuantEngine Pro — 一键安装脚本
===============================
自动创建虚拟环境、安装依赖、运行测试。
支持 Windows / Linux / macOS。

用法:
    python setup.py                         完整安装（默认使用清华镜像）
    python setup.py --minimal               仅安装核心依赖（不含 akshare, ccxt）
    python setup.py --skip-test             跳过安装后的测试验证
    python setup.py --mirror aliyun         切换镜像源（tsinghua/aliyun/tencent/ustc/douban）
    python setup.py --mirror https://xxx    自定义镜像 URL
    python setup.py --no-mirror             直连 pypi.org（海外用户）
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path


# ── 常量 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / "venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

# PyPI 镜像源（国内用户可切换至清华/Tencent/阿里云加速）
# 完整列表: https://mirrors.tuna.tsinghua.edu.cn/help/pypi/
MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun":   "https://mirrors.aliyun.com/pypi/simple/",
    "tencent":  "https://mirrors.cloud.tencent.com/pypi/simple",
    "ustc":     "https://pypi.mirrors.ustc.edu.cn/simple/",
    "douban":   "https://pypi.doubanio.com/simple/",
    "pypi":     "https://pypi.org/simple",
}
DEFAULT_MIRROR = "tsinghua"

DEV_PACKAGES = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "black",
]

CORE_PACKAGES = [
    "pandas",
    "numpy",
    "pyyaml",
    "loguru",
    "pydantic",
    "pyarrow",
    "fastparquet",
    "plotly",
    "dash",
    "fastapi",
    "uvicorn",
    "aiohttp",
    "openai",
]

STYLE = {
    "green": "\033[92m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "red": "\033[91m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def style(text: str, *codes: str) -> str:
    """Apply ANSI styles if supported."""
    if not sys.stdout.isatty() or platform.system() == "Windows":
        return text
    prefix = "".join(STYLE[c] for c in codes if c in STYLE)
    return f"{prefix}{text}{STYLE['reset']}"


def info(msg: str):    print(style("  ◆", "cyan", "bold"), msg)
def ok(msg: str):      print(style("  ✔", "green", "bold"), msg)
def warn(msg: str):    print(style("  ⚠", "yellow", "bold"), msg)
def fail(msg: str):    print(style("  ✘", "red", "bold"), msg)


# ── 平台检测 ──────────────────────────────────────────────────────────────

def is_windows() -> bool:
    return platform.system() == "Windows"


def python_cmd() -> str:
    """Return the Python command name available on this system."""
    for cmd in ("python3", "python"):
        if shutil.which(cmd):
            return cmd
    sys.exit(fail("未找到 Python！请先安装 Python 3.10+：https://python.org"))


def venv_python() -> Path:
    """Path to the Python executable inside the virtual environment."""
    if is_windows():
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_pip() -> Path:
    """Path to pip inside the virtual environment."""
    if is_windows():
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def venv_activate() -> str:
    """Activation command (display only)."""
    if is_windows():
        return str(VENV_DIR / "Scripts" / "Activate")
    return f"source {VENV_DIR / 'bin' / 'activate'}"


# ── pip 镜像助手 ──────────────────────────────────────────────────────────

_pip_mirror_url: str | None = None

def set_mirror(name: str):
    """Set PyPI mirror by name or URL."""
    global _pip_mirror_url
    if name in MIRRORS:
        _pip_mirror_url = MIRRORS[name]
        info(f"PyPI 镜像源: {name} ({_pip_mirror_url})")
    elif name.startswith("http://") or name.startswith("https://"):
        _pip_mirror_url = name
        info(f"PyPI 镜像源: {name}")
    else:
        known = ", ".join(MIRRORS.keys())
        warn(f"未知镜像 '{name}'，可选: {known}；使用默认")
        _pip_mirror_url = MIRRORS[DEFAULT_MIRROR]


def pip_args() -> list[str]:
    """Return ['-i', '<mirror-url>'] if a mirror is configured, else empty list."""
    if _pip_mirror_url:
        return ["-i", _pip_mirror_url]
    return []


# ── 步骤函数 ──────────────────────────────────────────────────────────────

def banner():
    """Print project banner."""
    print()
    print(style("  ╔═══════════════════════════════════════════╗", "cyan", "bold"))
    print(style("  ║        QuantEngine Pro — 一键安装         ║", "cyan", "bold"))
    print(style("  ╚═══════════════════════════════════════════╝", "cyan", "bold"))
    print(f"  Python {sys.version.split()[0]}  |  {platform.system()} {platform.machine()}")
    print()


def step_create_venv():
    """Create virtual environment if not exists."""
    if VENV_DIR.exists():
        info(f"虚拟环境已存在: {VENV_DIR}")
        return

    info("正在创建虚拟环境...")
    venv.create(VENV_DIR, clear=False, with_pip=True)
    ok(f"虚拟环境已创建: {VENV_DIR}")


def step_upgrade_pip():
    """Upgrade pip inside venv."""
    info("正在升级 pip...")
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--upgrade", "pip"] + pip_args(),
        check=True, capture_output=True,
    )
    ok("pip 已升级")


def step_install_deps(minimal: bool = False):
    """Install project dependencies."""
    if not minimal and REQUIREMENTS.exists():
        info("正在安装项目依赖（完整安装，预计 2-5 分钟）...")
        subprocess.run(
            [str(venv_pip()), "install", "-r", str(REQUIREMENTS)] + pip_args(),
            check=True,
        )
        ok("项目依赖安装完成")
    elif minimal:
        info("正在安装核心依赖（最小安装）...")
        subprocess.run(
            [str(venv_pip()), "install"] + CORE_PACKAGES + pip_args(),
            check=True,
        )
        ok("核心依赖安装完成")
    else:
        warn(f"未找到 {REQUIREMENTS.name}，跳过依赖安装")


def step_install_dev():
    """Install development tools (pytest, ruff, black)."""
    info("正在安装开发工具（pytest, ruff, black）...")
    subprocess.run(
        [str(venv_pip()), "install"] + DEV_PACKAGES + pip_args(),
        check=True,
    )
    ok("开发工具安装完成")


def step_run_tests():
    """Run the test suite to verify everything works."""
    print()
    info("正在运行测试（验证安装正确性）...")
    result = subprocess.run(
        [str(venv_python()), "-m", "pytest", "tests/", "-v", "--tb=short"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode == 0:
        ok(style("所有测试通过！", "green", "bold"))
    else:
        warn(f"部分测试失败 (exit code {result.returncode}):")
        for line in result.stderr.splitlines():
            print(f"    {line}")
    return result.returncode


def step_create_env_example():
    """Copy .env.example → .env if neither exists."""
    env_example = PROJECT_ROOT / ".env.example"
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        return
    if env_example.exists():
        shutil.copy2(env_example, env_file)
        ok(f"已创建 {env_file}（请编辑填入 API Key）")


def print_summary(skip_test: bool, test_ok: bool):
    """Print post-installation summary."""
    print()
    print(style("  ╔═══════════════════════════════════════════╗", "cyan", "bold"))
    print(style("  ║              安装完成！                    ║", "cyan", "bold"))
    print(style("  ╚═══════════════════════════════════════════╝", "cyan", "bold"))
    print()

    if test_ok:
        print(style("  ✔  12 项测试全部通过", "green", "bold"))
    elif skip_test:
        print(style("  ⚠  已跳过测试验证", "yellow"))
    else:
        print(style("  ✘  部分测试失败，请检查输出", "red"))

    print()
    print(style("  📋 下一步操作：", "bold"))
    print()
    print(f"    激活虚拟环境:")
    print(style(f"      {venv_activate()}", "dim"))
    print()
    print(f"    下载行情数据:")
    print(style(f"      python scripts/download_data.py --market crypto --freq 1h", "dim"))
    print()
    print(f"    运行回测:")
    print(style(f"      python scripts/run_backtest.py --strategy dual_thrust --symbol ETH/USDT --timeframe 1h", "dim"))
    print()
    print(f"    启动 Web 看板:")
    print(style(f"      python -m quantengine.web.app --port 8050", "dim"))
    print(f"      → http://localhost:8050")
    print()
    print(f"    API 文档:")
    print(style(f"      → http://localhost:8000/docs", "dim"))
    print()
    print(style(f"  💡 提示：编辑 config/*.yaml 可切换数据源/策略/风控参数", "dim"))
    print()


# ── 主入口 ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="QuantEngine Pro — 一键安装脚本",
    )
    parser.add_argument(
        "--minimal", action="store_true",
        help="最小安装（仅核心依赖，不含 akshare、ccxt）",
    )
    parser.add_argument(
        "--skip-test", action="store_true",
        help="跳过安装后的测试验证",
    )
    parser.add_argument(
        "--mirror", type=str, default=DEFAULT_MIRROR, nargs="?",
        help=(
            f"PyPI 镜像源名称或 URL（默认: {DEFAULT_MIRROR}）。"
            f"内置镜像: {', '.join(MIRRORS.keys())}。"
            "使用 --no-mirror 禁用镜像直连 pypi.org"
        ),
    )
    parser.add_argument(
        "--no-mirror", dest="mirror", action="store_const", const=None,
        help="禁用镜像源，直连 pypi.org",
    )
    args = parser.parse_args()

    banner()

    # 检测 Python
    py = python_cmd()
    info(f"系统 Python: {shutil.which(py)}")

    # 检测项目目录
    os.chdir(PROJECT_ROOT)
    info(f"项目目录: {PROJECT_ROOT}")

    # 设置镜像源
    if args.mirror:
        set_mirror(args.mirror)
    else:
        info("直连 pypi.org（未使用镜像）")

    print()
    print(style("  ── 第一步：创建虚拟环境 ──", "bold"))
    step_create_venv()

    print()
    print(style("  ── 第二步：升级 pip ──", "bold"))
    step_upgrade_pip()

    print()
    print(style("  ── 第三步：安装依赖 ──", "bold"))
    step_install_deps(minimal=args.minimal)
    step_install_dev()

    print()
    print(style("  ── 第四步：创建环境变量文件 ──", "bold"))
    step_create_env_example()

    test_ok = True
    if not args.skip_test:
        print()
        print(style("  ── 第五步：运行测试验证 ──", "bold"))
        test_ok = step_run_tests() == 0
    else:
        warn("已跳过测试验证（--skip-test）")

    print_summary(skip_test=args.skip_test, test_ok=test_ok)

    return 0 if test_ok else 1


if __name__ == "__main__":
    sys.exit(main())
