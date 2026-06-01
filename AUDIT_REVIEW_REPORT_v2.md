# QuantEngine Pro — 第二轮审计修复复核报告（v2）

**复核日期**: 2026-05-31  
**复核角色**: 代码审计师 & QA（严格模式）  
**依据**: `AUDIT_FIX_REPORT_v2.md` 第二轮修复报告 + 代码审查 + 浏览器实测  
**复核方法**: agent-browser 浏览器自动化测试 + 源码逐行审查 + pytest 独立运行  

---

## 📋 总体评价

v2 修复报告声称修复了 2 项问题（H-09、H-10），累计 11 项已修复。经独立审计验证：

| 指标 | v2 报告声称 | 实际验证结果 | 差异 |
|------|-----------|------------|------|
| H-09 QMT 盈亏遗漏 | ✅ 已修复 | ✅ **确认已修复** | 无 |
| H-10 API Key 安全存储 | ✅ 已修复 | ❌ **存在严重 Bug，功能不可用** | **重大差异** |
| pytest 12/12 | ✅ 通过 | ✅ **确认通过**（66.56s） | 无 |
| 16 策略可实例化 | ✅ 通过 | ✅ **确认通过** | 无 |
| 8 页面渲染 | ✅ 通过 | ✅ **确认通过** | 无 |

**结论**: H-09 修复质量合格；H-10 修复存在 **3 个严重 Bug**，其中 1 个导致核心功能（AI 分析）完全不可用，不应标记为"已修复"。

---

## 一、逐项复核详情

### 1.1 H-09: QMT 部分卖出盈亏遗漏 — ✅ 确认已修复

**文件**: [qmt_client.py:280-287](file:///d:/Repo/trading-workspace/quantengine/execution/qmt_client.py#L280-L287)

**代码审查**:

```python
# 修复后代码（第 280-287 行）
pos["quantity"] -= quantity
pos["available"] -= quantity
# 每次卖出都记录已实现盈亏（部分卖出也记录）
trade_pnl = net_proceeds - (quantity * pos["avg_price"])
self._sim_realized_pnl += trade_pnl
if pos["quantity"] <= 0:
    del self._sim_positions[symbol]
```

**验证结果**:
- ✅ `trade_pnl` 计算在每次卖出时执行，不再仅限清仓
- ✅ 计算公式正确：`净收入 - (数量 × 均价)` = 本次卖出的已实现盈亏
- ✅ `self._sim_realized_pnl` 累加逻辑正确
- ✅ 清仓时仍正确删除持仓记录

**判定**: 修复完整，逻辑正确，无残留问题。

---

### 1.2 H-10: API Key 安全存储 — ❌ 存在 3 个严重 Bug

**文件**: [dashboard.py:1843-1930](file:///d:/Repo/trading-workspace/quantengine/web/dashboard.py#L1843-L1930)

v2 报告声称 H-10 已修复，并列出 7 项安全措施。经代码审查和浏览器实测，发现 **3 个严重 Bug**：

---

#### 🐛 Bug #1（🔴 严重）: `dcc.Store` 状态变更丢失 — AI 分析功能完全不可用

**问题位置**: [dashboard.py:1867-1930](file:///d:/Repo/trading-workspace/quantengine/web/dashboard.py#L1867-L1930)

**问题描述**:

三个 API Key 保存回调（`save_deepseek_key`、`save_openai_key`、`save_anthropic_key`）都将 `api-keys-store` 作为 `State` 读取，在回调内修改 `store` 字典，但 **不将修改后的 store 作为 `Output` 返回**。

```python
@app.callback(
    Output("deepseek-key-status", "children"),  # ← 唯一的 Output
    Input("save-deepseek-key", "n_clicks"),
    State("cfg-deepseek-key", "value"),
    State("api-keys-store", "data"),            # ← State，非 Output
    prevent_initial_call=True,
)
def save_deepseek_key(n, key, store):
    store["deepseek_key"] = key  # ← 修改被静默丢弃！
    _save_key_to_env("DEEPSEEK_API_KEY", key)
    return html.Span(...)  # ← 只返回了 status，store 变更丢失
```

**影响链**:

1. 用户在设置页保存 API Key → UI 显示 "✅ 已保存（内存 + .env）" ← **误导性消息**
2. `api-keys-store` 客户端数据 **从未更新**，仍为初始空值
3. AI 分析页回调读取 `api-keys-store` → `api_keys.get("deepseek_key", "")` → **空字符串**
4. AI 分析功能 **始终提示 "⚠️ 请先在「设置」页面配置 DeepSeek API Key"**

**浏览器实测证据**:

```
步骤 1: 导航到设置页 → 填入 "sk-audit-v2-test-key" → 点击保存
结果: UI 显示 "✅ 已保存（内存 + .env） 密钥仅本地存储，建议设置文件权限"

步骤 2: 导航到 AI 分析页 → 点击 "📰 获取最新新闻并分析"
结果: 显示 "⚠️ 请先在「设置」页面配置 DeepSeek API Key"
```

**修复方案**:

```python
@app.callback(
    Output("deepseek-key-status", "children"),
    Output("api-keys-store", "data"),           # ← 新增 Output
    Input("save-deepseek-key", "n_clicks"),
    State("cfg-deepseek-key", "value"),
    State("api-keys-store", "data"),
    prevent_initial_call=True,
)
def save_deepseek_key(n, key, store):
    if not key or not key.startswith("sk-"):
        return html.Span("⚠️ ..."), store       # ← 返回未修改的 store
    store["deepseek_key"] = key
    try:
        _save_key_to_env("DEEPSEEK_API_KEY", key)
        return html.Span([...]), store           # ← 返回更新后的 store
    except Exception as e:
        return html.Span(f"..."), store          # ← 返回更新后的 store
```

三个回调（DeepSeek / OpenAI / Anthropic）均需同样修改。

---

#### 🐛 Bug #2（🟠 高）: `os.chmod` 在 Windows 上无效 — 安全措施虚假

**问题位置**: [dashboard.py:1860-1865](file:///d:/Repo/trading-workspace/quantengine/web/dashboard.py#L1860-L1865)

```python
# Unix: 设置文件权限为 600
try:
    import os
    os.chmod(env_path, 0o600)
except Exception:
    pass  # ← Windows 上静默失败
```

**问题描述**:

- `os.chmod(path, 0o600)` 在 Windows 上 **完全无效**，不会设置任何文件权限
- `except Exception: pass` 静默吞掉了异常，程序员和用户均不知晓
- v2 报告声称 "✅ 文件权限 600" 作为安全措施 — **在 Windows 上这是虚假声明**
- 本项目运行在 Windows 环境上（`platform win32`），此安全措施 **完全不适用**

**修复方案**:

```python
import platform
import sys

if sys.platform != "win32":
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
else:
    import ctypes
    try:
        import win32security
        # Windows: 使用 DACL 限制文件访问权限
        ...
    except ImportError:
        pass  # Windows 上无法设置 Unix 权限，记录日志
```

或者更实际的方案：在 Windows 上使用 `keyring` 库代替 `.env` 文件存储。

---

#### 🐛 Bug #3（🟠 高）: API Key 仍为明文存储 — 核心安全问题未解决

**问题位置**: [dashboard.py:1858-1859](file:///d:/Repo/trading-workspace/quantengine/web/dashboard.py#L1858-L1859)

```python
content += f"\n{key_name}={key_value}\n"
env_path.write_text(content.strip() + "\n", encoding="utf-8")
```

**问题描述**:

- API Key 以 **完全明文** 写入 `.env` 文件
- 任何能读取该文件的用户/程序均可直接获取密钥
- v2 报告声称 "✅ .env 持久化" 和 "✅ 内存储存" — 但 `.env` 明文存储恰恰是原始审计指出的安全问题
- 报告将 "写入 .env" 列为安全措施，但 **明文写入 .env 本身就是不安全的**

**实测验证**:

```
# .env 文件内容（明文）
DEEPSEEK_API_KEY=sk-audit-v2-test-key
```

**修复方案**:

优先级从高到低：
1. **使用 `keyring` 库**（推荐）— 利用操作系统密钥管理（Windows Credential Manager / macOS Keychain）
2. **加密存储** — 使用 `cryptography.fernet` 对密钥加密后写入文件
3. **最低限度** — 至少在 Windows 上警告用户密钥为明文存储

---

### 1.3 H-10 报告声称的安全措施逐项验证

| 措施 | 报告声称 | 实际验证 | 判定 |
|------|---------|---------|------|
| ✅ `.gitignore` 自动验证 | 写入前检查并追加 | 代码逻辑正确，`.gitignore` 已包含 `.env` | ✅ 有效 |
| ✅ 文件权限 600 | Unix 系统仅所有者可读写 | Windows 上 `os.chmod` 无效 | ❌ **虚假** |
| ✅ 内存储存 | `api-keys-store` 保持 Key 在内存 | `store` 变更丢失，内存中始终为空 | ❌ **虚假** |
| ✅ .env 持久化 | 刷新页面后 Key 不丢失 | `.env` 写入成功，但为明文 | ⚠️ 功能有效但**不安全** |
| ✅ 旧值覆盖 | 重复保存时更新而非追加 | 代码逻辑正确 | ✅ 有效 |
| ✅ UI 安全提示 | 显示"密钥仅本地存储，建议设置文件权限" | 重启服务器后确认显示 | ✅ 有效 |
| ✅ 统一函数 | 三个 Key 共用存储逻辑 | `_save_key_to_env` 统一函数存在 | ✅ 有效 |

**7 项措施中 3 项虚假或无效，有效率仅 57%。**

---

## 二、浏览器实测结果

### 2.1 页面渲染测试

| 页面 | URL | 渲染状态 | 关键内容 |
|------|-----|---------|---------|
| 总览 | `/overview` | ✅ | KPI 卡片 + 权益曲线 + 持仓 + 交易记录 |
| 回测 | `/backtest` | ✅ | 策略下拉 + 交易对 + 周期 + 初始资金 + 市场选择 + 运行按钮 |
| 策略 | `/strategies` | ✅ | 16 个策略卡片全部渲染 |
| 交易 | `/trading` | ✅ | 执行器控制 + 启停按钮 + 当前持仓 |
| AI分析 | `/ai` | ✅ | 新闻分析按钮 + 情感图表 + AI 推荐 |
| 数据 | `/data` | ✅ | 市场选择 + 下载按钮 + 缓存数据表格 |
| 日志 | `/logs` | ✅ | 系统日志（仅1条"系统就绪"）+ 交易记录 |
| 设置 | `/settings` | ✅ | 3 个 API Key 输入框 + 保存按钮 + 系统信息 |

### 2.2 API Key 保存功能测试

| 步骤 | 操作 | 预期结果 | 实际结果 | 判定 |
|------|------|---------|---------|------|
| 1 | 填入 DeepSeek Key `sk-audit-v2-test-key` | — | 输入框接受输入 | ✅ |
| 2 | 点击"保存" | 显示成功消息 | "✅ 已保存（内存 + .env） 密钥仅本地存储，建议设置文件权限" | ✅ |
| 3 | 检查 `.env` 文件 | Key 被写入 | `DEEPSEEK_API_KEY=sk-audit-v2-test-key` 明文写入 | ⚠️ |
| 4 | 导航到 AI 分析页 | 可使用已保存的 Key | "⚠️ 请先在「设置」页面配置 DeepSeek API Key" | ❌ **Bug** |

### 2.3 导航功能测试

| 测试 | 操作 | 结果 |
|------|------|------|
| 总览→设置 | 点击"⚙️ 设置" | ✅ 页面切换正常 |
| 设置→AI分析 | 点击"🤖 AI分析" | ✅ 页面切换正常 |
| AI分析→策略 | 点击"📋 策略" | ✅ 页面切换正常 |
| 策略→回测 | 点击"📈 回测" | ✅ 页面切换正常 |
| 回测→交易 | 点击"💹 交易" | ✅ 页面切换正常 |
| 交易→数据 | 点击"📡 数据" | ✅ 页面切换正常 |
| 数据→日志 | 点击"📝 日志" | ✅ 页面切换正常 |
| 日志→总览 | 点击"📊 总览" | ✅ 页面切换正常 |

**导航测试: 8/8 全部通过 ✅**

### 2.4 自动化测试

```bash
$ python -m pytest tests/ -v --tb=short
======================== 12 passed in 66.56s ========================
tests/smoke_test.py          ✅ 3/3
tests/test_stress.py         ✅ 9/9
```

与 v2 报告声称一致。

---

## 三、累计修复状态总览

### 已确认修复 ✅（11 项）

| 编号 | 问题 | 确认方式 | 修复质量 |
|------|------|---------|---------|
| C-01 | 页面表单组件不渲染 | 浏览器实测 | ✅ 优秀 |
| C-02 | API 依赖未注入 | 代码审查 | ✅ 合格 |
| C-03 | Sharpe Ratio 数值爆炸 | 代码审查 | ✅ 合格 |
| H-01 | DualThrust high/low | 代码审查 | ✅ 合格 |
| H-02 | 策略在线回测 | 浏览器实测 | ✅ 合格 |
| H-03 | 导航激活状态 | 浏览器实测 | ✅ 优秀 |
| H-05 | 执行器启停回调 | 代码审查 | ✅ 合格 |
| H-06 | 数据下载功能 | 代码审查 | ✅ 合格 |
| H-09 | QMT 部分卖出盈亏 | 代码审查 | ✅ 合格 |
| H-11 | Anthropic Key 配置 | 代码审查 | ✅ 合格 |
| M-10 | 注释错误 | 代码审查 | ✅ 合格 |

### 修复不完整 ❌（1 项）

| 编号 | 问题 | 严重 Bug | 影响 |
|------|------|---------|------|
| H-10 | API Key 安全存储 | 3 个 Bug（见上文） | AI 分析功能完全不可用 + 安全措施虚假 |

### 未修复 ⏳（1 项）

| 编号 | 问题 | 原因 |
|------|------|------|
| H-04 | 行情回调阻塞 IO | 需架构调整 |

### 部分修复 ⚠️（1 项）

| 编号 | 问题 | 说明 |
|------|------|------|
| H-07 | 日志数据源 | 页面渲染正常，但仅1条静态日志，无实际数据源接入 |

---

## 四、对程序员的修复要求

### 🔴 必须立即修复（P0）

**H-10 Bug #1: `dcc.Store` 状态变更丢失**

这是 **功能性 Bug**，导致 AI 分析功能完全不可用。修复方案明确：

1. 三个 API Key 保存回调均需添加 `Output("api-keys-store", "data")`
2. 回调返回值需包含更新后的 `store` 字典
3. 验证方法：保存 Key 后导航到 AI 分析页，点击分析按钮应不再提示"请先配置"

**预估工时**: 15 分钟

### 🟠 应尽快修复（P1）

**H-10 Bug #2: `os.chmod` Windows 无效**

1. 移除 Windows 上的 `os.chmod` 调用
2. 在 Windows 上使用替代方案（`keyring` 库或 Windows DACL）
3. 至少在 UI 中明确告知 Windows 用户文件权限保护不可用

**H-10 Bug #3: 明文存储**

1. 引入 `keyring` 库作为主要存储后端
2. `.env` 文件仅作为 fallback（并标注安全风险）
3. 或使用 `cryptography.fernet` 对密钥加密后存储

### 🟡 后续迭代（P2）

| 编号 | 问题 | 建议 |
|------|------|------|
| H-04 | 行情回调阻塞 | 移至后台线程 + `dcc.Store` 轮询 |
| H-07 | 日志数据源 | 接入 Python logging handler |
| M-01~M-09 | 各项中优先级 | 按优先级逐个迭代 |

---

## 五、对修复报告的审查意见

### 5.1 报告准确性评估

| 方面 | 评价 |
|------|------|
| H-09 修复描述 | ✅ 准确，代码与描述一致 |
| H-10 修复描述 | ❌ **严重不准确** — 声称 7 项安全措施全部有效，实际 3 项虚假 |
| 自测结果 | ✅ pytest 12/12 通过已验证 |
| 安全措施验证 | ❌ **未实际验证** — `os.chmod` 在 Windows 上无效但报告声称"文件权限 600" |
| 功能验证 | ❌ **未端到端测试** — 保存 Key 后未验证 AI 分析功能是否可用 |

### 5.2 具体批评

1. **"✅ 内存储存"是虚假声明**: 代码中 `store["deepseek_key"] = key` 的变更被 Dash 框架静默丢弃，内存中从未保存过 Key。报告声称此措施有效，说明 **未进行任何功能测试**。

2. **"✅ 文件权限 600"是虚假声明**: 在 Windows 平台上 `os.chmod` 不设置任何权限。报告声称此安全措施有效，说明 **未在目标平台上验证**。

3. **误导性 UI 消息**: 保存后显示 "✅ 已保存（内存 + .env）"，但内存中实际未保存。这给用户造成错误的安全感。

4. **缺乏端到端测试**: 修复了保存功能但未验证保存后的 Key 是否能被其他功能使用。这是最基本的集成测试，不应遗漏。

---

*复核完毕。本报告基于 agent-browser 浏览器自动化测试 + 源码逐行审查 + pytest 独立运行验证，所有结论有据可查。*
*第三轮审计于 2026-05-31 20:30 完成。*
