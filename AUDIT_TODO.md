# QuantEngine Pro 代码审计与前端测试报告

**审计日期**: 2026-05-31  
**审计角色**: 代码审计师 & QA  
**审计范围**: 全项目代码 + Web前端浏览器实测  
**设计文档版本**: v2.0  

---

## 一、审计总结

| 类别 | 严重 | 高 | 中 | 低 |
|------|------|---|---|---|
| 前端渲染缺陷 | 2 | 2 | 1 | 0 |
| 回测引擎缺陷 | 0 | 2 | 1 | 0 |
| 策略层缺陷 | 0 | 1 | 1 | 0 |
| 数据层缺陷 | 0 | 1 | 2 | 0 |
| 执行层缺陷 | 0 | 1 | 1 | 0 |
| 分析服务层缺陷 | 0 | 1 | 1 | 0 |
| 架构/集成缺陷 | 1 | 2 | 2 | 0 |
| 安全缺陷 | 0 | 1 | 1 | 0 |
| **合计** | **3** | **11** | **10** | **0** |

---

## 二、严重问题 (Critical)

### C-01: 回测/数据/设置页面表单组件不渲染

**文件**: `quantengine/web/dashboard.py`  
**现象**: 通过浏览器实测发现，回测页面、数据下载页面、设置页面的表单组件（Dropdown、Input、Button）完全不渲染。页面 DOM 中仅存在 `bt-progress` 和 `bt-results` 两个空 div，策略选择下拉框、交易对输入框、运行回测按钮等关键交互元素全部缺失。  
**根因**: `_section()` 函数返回的 `html.Div` 包含 `dcc.Dropdown` / `dcc.Input` 等 Dash 核心组件，但 Dash 在客户端渲染时未能正确处理这些嵌套在无 ID 容器中的交互组件。Dash 要求所有交互组件（带 `id` 的组件）在 layout 中预先声明或通过正确的 callback 返回。当前 `_page_backtest()` 返回的完整布局中，`_section()` 包裹的表单组件被 Dash 客户端静默丢弃。  
**影响**: 用户无法在 Web 界面进行回测配置、数据下载、API 密钥配置，核心功能完全不可用。  
**修复指导**:
1. 将回测页面的表单组件（`bt-strategy`、`bt-symbol` 等）的 ID 在主 layout 中预先声明为隐藏元素，或改用 `dcc.Tabs` + `dcc.Tab` 替代自定义侧边栏导航
2. 更根本的方案：将所有页面的交互组件 ID 在 `app.layout` 中注册，确保 Dash 的 component registry 能追踪这些组件
3. 临时方案：在 `_page_backtest()` 中不使用 `_section()` 包裹，直接返回扁平的组件列表

### C-02: API 模块全局依赖未注入

**文件**: `quantengine/web/api.py` (L20-24), `quantengine/web/app.py` (L42-53)  
**现象**: FastAPI 后端所有 API 端点返回空数据（`{"data":[]}`, `{"strategies":[]}`, `{"available":false}`）。  
**根因**: `api.py` 顶部声明了全局变量 `backtest_engine = None`, `strategy_registry = None` 等，但 `app.py` 启动时仅调用 `create_app()` 创建了 FastAPI 实例，从未将这些依赖注入到 api 模块中。`dashboard.py` 有 `set_globals()` 函数但同样未被调用。  
**影响**: REST API 完全不可用，WebSocket 推送空数据，前端无法获取任何后端状态。  
**修复指导**:
1. 在 `app.py` 的 `main()` 中，创建 `BacktestEngine`、`StrategyRegistry` 等实例后，调用 `api.backtest_engine = engine` 等赋值
2. 或改为依赖注入模式：`create_app(engine, registry, ...)` 参数传入
3. 同时调用 `set_globals()` 将实例传递给 dashboard

### C-03: Sharpe Ratio 计算数值爆炸

**文件**: `quantengine/backtest/analyzer.py` (L175-184)  
**现象**: Smoke test 输出 `sharpe=-46434828084505216.00`，数值完全异常。  
**根因**: 当回测无交易发生时，权益曲线不变，`daily_return` 全为 0 或 NaN。`excess = returns - risk_free_rate/252` 产生微小负值序列，其 `std()` 极小但不为 0，导致 `mean/std` 比值爆炸。  
**影响**: 绩效报告中的 Sharpe/Sortino 等关键指标完全不可信，误导策略评估。  
**修复指导**:
```python
def _calc_sharpe(self, returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    excess = returns - self.risk_free_rate / 252
    std = excess.std()
    if std < 1e-10:  # 增加下界保护
        return 0.0
    return (excess.mean() / std) * math.sqrt(252)
```
同样修复 `_calc_sortino()` 中的类似问题。

---

## 三、高优先级问题 (High)

### H-01: DualThrust 策略逻辑错误 — HH/HC 使用 close 而非 high

**文件**: `quantengine/strategy/builtin/dual_thrust.py` (L53-56)  
**现象**: DualThrust 策略在 smoke test 中产生 0 笔交易。  
**根因**: 原始 Dual Thrust 算法定义：
- HH = N日最高价的最大值
- LC = N日最低价的最小值  
- HC = N日最高价的最大值
- LL = N日最低价的最小值

但当前代码全部使用 `close` 价格计算：
```python
hh = np.max(close[-self.period:])  # 应为 high
lc = np.min(close[-self.period:])  # 应为 low
hc = np.max(close[-self.period:])  # 应为 high
ll = np.min(close[-self.period:])  # 应为 low
```
导致 `hh == hc` 且 `lc == ll`，Range 计算退化，突破阈值不合理。  
**修复指导**:
```python
hh = np.max(high[-self.period:])
lc = np.min(low[-self.period:])
hc = np.max(high[-self.period:])
ll = np.min(low[-self.period:])
```

### H-02: 回测页面缺少 5 个策略的在线回测支持

**文件**: `quantengine/web/dashboard.py` (L1233-1245)  
**现象**: `STRATEGY_CLASSES` 字典仅包含 11 个策略，缺少 `pivot_point`、`fei_ali`、`dynamic_breakout_ii`、`multi_factor`、`sector_rotation`。  
**影响**: 用户在 Web 界面选择这 5 个策略时，会收到"不支持在线回测"的提示。  
**修复指导**: 在 `STRATEGY_CLASSES` 中补充缺失策略的导入和默认参数：
```python
from quantengine.strategy.builtin.pivot_point import PivotPointStrategy
from quantengine.strategy.builtin.fei_ali import FeiAliStrategy
from quantengine.strategy.builtin.dynamic_breakout_ii import DynamicBreakoutIIStrategy
from quantengine.strategy.builtin.multi_factor import MultiFactorStrategy
from quantengine.strategy.builtin.sector_rotation import SectorRotationStrategy

STRATEGY_CLASSES = {
    ...
    "pivot_point": (PivotPointStrategy, {}),
    "fei_ali": (FeiAliStrategy, {}),
    "dynamic_breakout_ii": (DynamicBreakoutIIStrategy, {}),
    "multi_factor": (MultiFactorStrategy, {}),
    "sector_rotation": (SectorRotationStrategy, {}),
}
```

### H-03: 侧边栏导航无激活状态高亮

**文件**: `quantengine/web/dashboard.py` (L181-203, L1171-1187)  
**现象**: 浏览器实测确认，点击任何导航项后，所有导航项颜色保持一致（`#9ca3af`），无法识别当前所在页面。  
**根因**: `navigate` 回调更新了 `page-content` 和 `page-title`，但没有更新各导航项的样式。  
**修复指导**: 在 `navigate` 回调中增加对各 `nav-{id}` 元素 style 的 Output，根据当前页面设置激活项的背景色和文字色。或使用 Dash 的 `dcc.Link` + `dcc.Location` 实现标准 URL 路由。

### H-04: 实时行情回调在 Dash 请求上下文中运行阻塞 IO

**文件**: `quantengine/web/dashboard.py` (L1352-1507)  
**现象**: `refresh_market_data` 回调使用 `concurrent.futures.ThreadPoolExecutor` 在 Dash 回调线程中执行网络请求（akshare、CCXT），每次请求可能耗时 5-10 秒，阻塞 Dash 的回调处理线程。  
**影响**: 行情刷新期间，整个 Dash 应用无法响应其他回调（导航、回测等），用户体验卡顿。  
**修复指导**:
1. 将行情获取逻辑移到独立的后台线程/进程，通过 `dcc.Store` + `dcc.Interval` 轮询结果
2. 或使用 Celery / BackgroundScheduler 异步执行，将结果写入 Redis 供 Dash 读取
3. 减少行情刷新频率（当前 5 秒过于频繁），改为 30 秒或 60 秒

### H-05: 执行器启动/停止按钮无回调

**文件**: `quantengine/web/dashboard.py` (L862-875)  
**现象**: 交易页面的"启动执行器"和"停止执行器"按钮（`exec-start-btn`、`exec-stop-btn`）没有注册任何 Dash callback。  
**影响**: 用户点击按钮无任何反应，实盘执行器无法通过 Web 界面控制。  
**修复指导**: 在 `_register_callbacks()` 中添加对应的回调函数，调用 `LiveExecutor` 的 `start()` / `stop()` 方法。

### H-06: 数据下载按钮仅返回 CLI 提示

**文件**: `quantengine/web/dashboard.py` (L1322-1344)  
**现象**: 点击"开始下载"按钮后，仅显示"请使用命令行"的提示信息，不执行实际下载。  
**影响**: 用户无法通过 Web 界面下载数据，与设计文档中"数据下载"功能不符。  
**修复指导**: 实现实际的下载回调，调用 `AkshareQuoteFetcher` / `CCXTQuoteFetcher` 的 `fetch_kline()` 方法，将结果存入 Parquet。

### H-07: 日志页面缺少系统日志区域

**文件**: `quantengine/web/dashboard.py` (L1123-1146)  
**现象**: 浏览器实测发现日志页面仅显示"交易记录"部分，"系统日志"部分不可见。与 C-01 同根因——含交互组件的 `_section()` 未渲染。  
**修复指导**: 同 C-01 修复方案。

### H-08: Redis 依赖未安装导致二级缓存不可用

**文件**: `quantengine/data/cache.py`, `requirements.txt`  
**现象**: Smoke test 输出 `Redis not available (No module named 'redis'), Redis cache disabled`。  
**影响**: 系统仅使用内存 LRU + Parquet 文件缓存，缺少 Redis 热数据缓存层，频繁请求免费数据源时容易触发限流。  
**修复指导**:
1. 在 `requirements.txt` 中确认 `redis>=5.0` 已列出（已列出）
2. 在部署文档中说明需安装 Redis 服务
3. 在 `cache.py` 中增加 Redis 连接重试和降级逻辑

### H-09: QMT 客户端模拟模式卖出时已实现盈亏计算错误

**文件**: `quantengine/execution/qmt_client.py` (L283-285)  
**现象**: 当清仓卖出时（`pos["quantity"] <= 0`），计算 `realized_pnl` 使用的是 `quantity`（本次卖出量）而非累计持仓量，且先删除了 position 再计算。  
**根因**: 代码逻辑：
```python
pos["quantity"] -= quantity
pos["available"] -= quantity
if pos["quantity"] <= 0:
    self._sim_realized_pnl += net_proceeds - (quantity * pos["avg_price"])
    del self._sim_positions[symbol]
```
`quantity` 在此处已被减去，实际应使用减去前的持仓量来计算盈亏。  
**修复指导**:
```python
pos["quantity"] -= quantity
pos["available"] -= quantity
if pos["quantity"] <= 0:
    self._sim_realized_pnl += net_proceeds - (pos["quantity"] + quantity) * pos["avg_price"]
    del self._sim_positions[symbol]
```
或在减去 quantity 之前先保存原始持仓量。

### H-10: API 密钥明文写入 .env 文件

**文件**: `quantengine/web/dashboard.py` (L1523-1533, L1553-1563)  
**现象**: 保存 DeepSeek/OpenAI API Key 时，直接将密钥明文追加到 `.env` 文件。  
**影响**: API 密钥泄露风险，尤其是当 `.env` 文件被意外提交到版本控制时。  
**修复指导**:
1. 确保 `.env` 在 `.gitignore` 中
2. 考虑使用操作系统密钥管理（keyring 库）或加密存储
3. 至少在写入前检查文件权限

### H-11: 缺少 Anthropic API Key 配置入口

**文件**: `quantengine/web/dashboard.py` (L1009-1120)  
**现象**: 设置页面有 DeepSeek 和 OpenAI 的 Key 输入框，但设计文档提到支持 Anthropic 升级路径，而前端缺少 Anthropic Key 配置。  
**修复指导**: 在设置页面增加 Anthropic API Key 输入框，并在 `api-keys-store` 中增加 `anthropic_key` 字段。

---

## 四、中优先级问题 (Medium)

### M-01: A股/美股实时行情获取频繁失败

**文件**: `quantengine/web/dashboard.py` (L1380-1447)  
**现象**: 浏览器实测显示行情区域标注"模拟行情"，说明真实 API 调用失败。  
**根因**: `ak.stock_zh_a_spot_em()` 和 `ak.stock_us_famous_spot_em()` 在高频调用时容易触发东方财富的反爬机制；且 `stock_us_famous_spot_em()` 函数名可能已在新版 akshare 中变更。  
**修复指导**:
1. 增加请求间隔控制和 User-Agent 伪装
2. 使用 akshare 的 `stock_zh_index_daily_em()` 等更稳定的接口获取指数数据
3. 对 akshare API 调用增加 try-except 和版本兼容检查

### M-02: 缺少 Optuna 参数优化 UI

**文件**: `quantengine/web/dashboard.py`  
**现象**: 设计文档阶段2要求"Optuna参数优化"，但 Web 界面无此功能入口。`scripts/optimize.py` 存在但未集成到前端。  
**修复指导**: 在回测页面增加"参数优化"按钮，调用 Optuna 进行超参搜索，结果展示最优参数和优化历史图。

### M-03: 缺少月度/年度收益热力图

**文件**: `quantengine/backtest/analyzer.py` (L289-314)  
**现象**: `PerformanceAnalyzer` 已实现 `_calc_monthly_returns()` 方法，但 dashboard 的回测结果展示中未使用此数据绘制热力图。  
**修复指导**: 在 `_build_backtest_results()` 中增加月度收益热力图（Plotly Heatmap）。

### M-04: 缺少基准对比功能

**文件**: `quantengine/web/dashboard.py`, `quantengine/backtest/analyzer.py`  
**现象**: `PerformanceAnalyzer` 支持 `benchmark_returns` 参数和 `_calc_benchmark_comparison()` 方法，但回测引擎和前端均未传入基准数据。  
**修复指导**: 在回测配置中增加"基准"选项（沪深300/BTC），回测时同步获取基准数据并传入 analyzer。

### M-05: 缺少多策略并行回测 UI

**文件**: `quantengine/web/dashboard.py`  
**现象**: 设计文档要求"多策略资金竞争"，但当前回测页面仅支持单策略回测。  
**修复指导**: 增加多策略选择（多选下拉框）和资金权重配置，调用 `engine.add_strategy()` 添加多个策略。

### M-06: 缺少风控参数配置 UI

**文件**: `quantengine/web/dashboard.py`  
**现象**: 设计文档要求"单标的上限、日亏损熔断、保证金监控"等风控参数可配置，但前端无此功能。  
**修复指导**: 在设置页面或回测配置中增加风控参数面板。

### M-07: 缺少 HTML/PDF 报告导出

**文件**: `quantengine/backtest/analyzer.py`  
**现象**: 设计文档要求"生成HTML/PDF报告"，但当前仅返回 Dict 格式的报告数据，无导出功能。  
**修复指导**: 使用 Plotly 的 `write_html()` 或 WeasyPrint 生成可下载的报告文件。

### M-08: WebSocket 推送数据为空

**文件**: `quantengine/web/api.py` (L113-129)  
**现象**: WebSocket 端点每秒推送 `{"equity": 0, "positions": []}`，因为 `backtest_engine` 和 `live_executor` 均为 None。  
**修复指导**: 同 C-02，注入依赖后 WebSocket 即可正常推送。

### M-09: 缺少 Toast 通知实现

**文件**: `quantengine/web/dashboard.py` (L163)  
**现象**: layout 中声明了 `html.Div(id="toast-container")`，但没有任何回调向其写入内容。  
**修复指导**: 实现一个 toast 通知系统，在回测完成、数据下载完成等事件时显示临时通知。

### M-10: `_page_settings()` 函数位置注释错误

**文件**: `quantengine/web/dashboard.py` (L1009)  
**现象**: `_page_settings()` 函数上方的注释写的是"页面：日志"，实际应为"页面：设置"。`_page_logs()` 在 L1123 才定义。  
**修复指导**: 修正注释为 `# 页面：设置`。

---

## 五、前端浏览器测试详细记录

### 测试环境
- **URL**: http://127.0.0.1:8050
- **浏览器**: Chromium (agent-browser headless)
- **API**: http://127.0.0.1:8000

### 页面测试结果

| 页面 | 导航 | 内容渲染 | 交互功能 | 结果 |
|------|------|----------|----------|------|
| 总览 | ✅ 正常 | ⚠️ 部分渲染（行情条仅显示加密货币，A股/美股区域不可见） | ⚠️ 行情刷新正常但回退到模拟数据 | 部分通过 |
| 回测 | ✅ 正常 | ❌ 配置表单完全不渲染，仅显示空进度条和结果区 | ❌ 无法运行回测 | 不通过 |
| 策略 | ✅ 正常 | ✅ 16个策略卡片全部显示 | ✅ 无交互需求 | 通过 |
| 交易 | ✅ 正常 | ⚠️ KPI卡片和按钮显示，但按钮无回调 | ❌ 启动/停止按钮无功能 | 部分通过 |
| AI分析 | ✅ 正常 | ⚠️ 部分渲染（情感图表区域显示，但获取新闻按钮可能不渲染） | ❌ 无法测试（需API Key） | 未验证 |
| 数据 | ✅ 正常 | ❌ 下载配置表单不渲染，仅显示缓存数据表 | ❌ 无法下载数据 | 不通过 |
| 日志 | ✅ 正常 | ⚠️ 仅显示交易记录，系统日志区域不渲染 | ✅ 无交互需求 | 部分通过 |
| 设置 | ✅ 标题切换 | ❌ 页面内容不更新，显示上一页面内容 | ❌ 无法配置API Key | 不通过 |

### API 端点测试结果

| 端点 | 状态 | 返回数据 | 结果 |
|------|------|----------|------|
| GET /api/health | 200 | `{"status":"ok"}` | ✅ 通过 |
| GET /api/equity | 200 | `{"data":[]}` | ❌ 空数据 |
| GET /api/positions | 200 | `{"positions":[]}` | ❌ 空数据 |
| GET /api/trades | 200 | `{"trades":[]}` | ❌ 空数据 |
| GET /api/strategies | 200 | `{"strategies":[]}` | ❌ 空数据 |
| GET /api/market/overview | 200 | `{"available":false}` | ❌ 不可用 |
| POST /api/backtest/run | 200 | `{"status":"not_implemented"}` | ❌ 未实现 |
| GET /api/llm/analysis/BTC | 200 | `{"available":false}` | ❌ 不可用 |
| WS /ws | 连接成功 | `{"equity":0,"positions":[]}` | ❌ 空数据 |

### Smoke Test 结果

```
✓ ALL SMOKE TESTS PASSED
⚠ Backtest Engine: 499 bars, Return: 0.00%, Sharpe: -46434828084505216.00, Max DD: 0.00%, Trades: 0
⚠ Redis not available, Redis cache disabled
```

---

## 六、与设计文档的差距分析

| 设计文档要求 | 当前状态 | 差距 |
|-------------|----------|------|
| Web看板实时权益曲线 | ⚠️ 图表存在但无数据 | API依赖未注入 |
| 回测参数配置→运行→可视化 | ❌ 配置表单不渲染 | C-01 |
| 16个内置策略在线回测 | ⚠️ 仅11个可在线回测 | H-02 |
| 多策略资金竞争 | ❌ 仅支持单策略 | M-05 |
| Optuna参数优化 | ❌ 无UI | M-02 |
| LLM新闻情感分析 | ⚠️ 代码存在但需API Key | 需配置 |
| 自动选股 | ⚠️ 后端代码存在，无前端 | 需集成 |
| 买卖点推荐WebSocket推送 | ❌ WebSocket数据为空 | M-08 |
| 实盘执行器启停 | ❌ 按钮无回调 | H-05 |
| 风控参数配置 | ❌ 无UI | M-06 |
| 每日报告生成推送 | ⚠️ 后端代码存在，无前端触发 | 需集成 |
| 月度/年度收益热力图 | ❌ 后端计算存在，前端未展示 | M-03 |
| 基准对比 | ❌ 后端支持，前端未集成 | M-04 |
| HTML/PDF报告导出 | ❌ 未实现 | M-07 |
| 数据一键下载 | ❌ 仅返回CLI提示 | H-06 |
| API密钥安全配置 | ⚠️ 明文存储 | H-10 |

---

## 七、修复优先级建议

### 第一批（阻塞性 — 必须立即修复）
1. **C-01**: 修复页面表单组件不渲染问题
2. **C-02**: 注入 API 模块全局依赖
3. **C-03**: 修复 Sharpe Ratio 数值爆炸
4. **H-01**: 修复 DualThrust 策略逻辑错误

### 第二批（核心功能 — 本周修复）
5. **H-02**: 补充5个缺失策略的在线回测
6. **H-03**: 添加侧边栏激活状态高亮
7. **H-05**: 实现执行器启停回调
8. **H-06**: 实现数据下载功能
9. **H-09**: 修复QMT模拟盈亏计算

### 第三批（体验优化 — 下周修复）
10. **H-04**: 行情刷新改为后台异步
11. **H-10**: API密钥安全存储
12. **M-01**: A股/美股行情稳定性
13. **M-08**: WebSocket数据注入
14. **M-09**: Toast通知系统

### 第四批（功能完善 — 后续迭代）
15. **M-02**: Optuna参数优化UI
16. **M-03**: 月度收益热力图
17. **M-04**: 基准对比功能
18. **M-05**: 多策略并行回测
19. **M-06**: 风控参数配置UI
20. **M-07**: HTML/PDF报告导出

---

## 八、附录：关键文件索引

| 文件 | 关键问题 |
|------|----------|
| `quantengine/web/dashboard.py` | C-01, H-02, H-03, H-04, H-05, H-06, H-10, H-11, M-09, M-10 |
| `quantengine/web/api.py` | C-02, M-08 |
| `quantengine/web/app.py` | C-02 |
| `quantengine/backtest/analyzer.py` | C-03, M-03, M-04, M-07 |
| `quantengine/strategy/builtin/dual_thrust.py` | H-01 |
| `quantengine/execution/qmt_client.py` | H-09 |
| `quantengine/data/cache.py` | H-08 |

---

*审计完毕。本文档仅供开发团队参考修复，不修改任何项目源代码文件。*
