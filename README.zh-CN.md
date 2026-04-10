# Daily Briefing

[English](README.md) | [中文](README.zh-CN.md)

面向个人投资组合的自动化金融情报系统。从 6+ 个数据源持续采集行情、新闻和 SEC 公告，利用 AI 消除媒体偏见，生成统一的每日简报，并提供交互式新闻关系图谱。

## 解决的问题

财经新闻嘈杂、带有立场、且分散在各处。同一份财报，一家媒体说"强劲增长势头"，另一家却说"增速放缓"。想要追踪地缘政治事件、利率决议、宏观趋势对自己持仓的影响，每天需要翻看多个信息源。

## 核心功能

- **采集** — 从 6 个数据源持续采集行情、新闻和 SEC 公告（免费源每 2 小时自动轮询）
- **中立化** — 利用大语言模型去除编辑偏见，仅保留经多方验证的事实，标注信源分歧
- **情绪打分** — 对每只持仓股票打出 -1.0 到 +1.0 的情绪分，并给出理由
- **可视化** — 通过交互式力导向图谱（News Map）展示新闻与持仓的关联
- **推送** — 将精美简报呈现在 Web 仪表板上，或通过邮件发送

## 快速开始

```bash
# 安装
pip install -e .

# 运行
python -m briefing
# 打开 http://localhost:8000
```

1. 进入 **Portfolio（投资组合）** — 添加你的持仓代码（如 AAPL、MSFT、VOO）
2. 进入 **Settings（设置）** — 配置 LLM 服务商（也可跳过，使用原始新闻模式）
3. 在仪表板点击 **Generate Now（立即生成）**

### Docker 部署

```bash
docker-compose up --build
# 打开 http://localhost:8000
```

## 功能详情

### 新闻采集（6 个数据源）

| 数据源 | 免费 | 需要密钥 | 提供内容 |
|--------|------|---------|---------|
| Yahoo Finance | 是 | 否 | 行情报价 + 新闻 |
| Google News RSS | 是 | 否 | 按股票代码搜索新闻 |
| 财经 RSS（CNBC、MarketWatch、Reuters） | 是 | 否 | 综合财经 + 宏观新闻 |
| SEC EDGAR | 是 | 否 | 10-K、10-Q、8-K 等公告 |
| NewsAPI | 免费 100 次/天 | 是 | 扩展新闻覆盖 |
| Alpha Vantage | 免费 25 次/天 | 是 | 补充行情 + 新闻情绪 |

**无需任何 API 密钥即可运行。** 三个免费数据源开箱即提供完整覆盖。在设置中添加 NewsAPI 和 Alpha Vantage 密钥可获得更广泛的新闻来源。

### 后台采集

免费数据源每 2 小时自动轮询一次。文章按 URL 去重后缓存到数据库。生成简报时直接从缓存读取（瞬间完成），无需重新抓取（省去 5-10 秒等待）。

### AI 驱动的新闻中立化

配置 LLM 后，每次生成简报时：

1. **聚类** — 将所有文章按报道主题分组（同一事件归为一组，即使涉及不同股票）
2. **中立化** — 去除主观用语，仅提取被 2 个以上信源证实的事实
3. **情绪评分** — 对每只股票打分（-1.0 到 +1.0），附带一行理由说明
4. **偏见标记** — 标注信源之间的分歧或带有倾向性的措辞

未配置 LLM 时，简报仍会生成，但以原始文章分组展示（无中立化处理和情绪分析）。

### 新闻图谱（News Map）

全屏暗色主题的交互式关系图谱，展示新闻与持仓的关联：

- **股票节点**（蓝色矩形） — 你的持仓
- **新闻节点**（情绪色边框矩形） — 经中立化处理的新闻聚类，连接到相关股票
- **MARKET 节点**（琥珀色菱形） — 宏观/地缘政治新闻的中枢节点（美联储、关税、通胀等）
- **连线** — 按情绪着色（绿色 = 正面，红色 = 负面，灰色 = 中性）
- **详情面板** — 点击任意节点查看完整报道、事实要点、信源和逐股影响分析
- 缩放控件、键盘快捷键（Escape 关闭面板）、移动端适配

### 宏观/地缘政治新闻

即使新闻未提及具体股票代码，系统仍会捕获影响整体市场的一般性新闻（利率决议、贸易战、通胀数据等）。RSS 采集器通过关键词匹配覆盖 30+ 个宏观主题。这些新闻在图谱中连接到 MARKET 中枢节点。

### LLM 服务商（支持 4 个）

| 服务商 | 需要密钥 | 说明 |
|--------|---------|------|
| Anthropic（Claude） | 是 | 默认推荐，建议使用 `claude-haiku-4-5-20251001` |
| OpenAI（GPT） | 是 | 支持 GPT-4 和 GPT-3.5 系列 |
| 阿里云通义千问（Qwen） | 是 | 通过 DashScope API（OpenAI 兼容接口） |
| Ollama | 否 | 本地部署，支持 llama3、mistral 等已安装模型 |

在设置中配置，同一时间只有一个服务商生效。

### 生成体验

点击"Generate Now"后，生成管道在后台运行。仪表板每 2 秒轮询一次显示进度卡片。如果你导航到其他页面，简报完成时会弹出 Toast 通知。

### 邮件推送

可选功能。在设置中配置 SMTP，即可在计划时间自动接收简报邮件。

## 配置说明

所有设置通过 `/settings` 页面管理，加密存储在数据库中（无需 `.env` 文件）。

**最简 `config.yaml`**（可选，仅用于指定数据库路径）：

```yaml
database:
  path: "./data/briefing.db"
```

其余所有配置（LLM 密钥、定时任务、邮件）均在设置页面操作，自动持久化到数据库。

### 定时任务

- **投递时间**：每日简报自动生成的时间（默认 07:00）
- **时区**：你的本地时区（默认 America/New_York）
- **后台采集**：免费数据源每 2 小时轮询（始终开启）

## 系统架构

```
                    APScheduler 定时任务
                    +-----------+
                    | 每 2 小时  |-----> 免费采集器 -----> news_articles（缓存）
                    | 每日定时   |-----> run_briefing() -----> briefings + sections
                    +-----------+
                         |
     FastAPI (端口 8000)  |
     +-------------------+-------------------+
     |                   |                   |
   仪表板             新闻图谱             投资组合
   (HTMX)           (Cytoscape.js)       (HTMX)
     |
  立即生成 ---> asyncio.create_task()
                        |
                    生成管道：
                    1. 读取文章缓存（24 小时内）
                    2. 实时获取行情报价
                    3. 运行付费采集器（如已配置密钥）
                    4. 合并缓存 + 新采集的文章
                    5. LLM 聚类 + 中立化处理
                    6. 渲染 HTML + 图谱数据
                    7. 存储简报
```

**技术栈**：Python 3.12+ / FastAPI / SQLAlchemy / SQLite / APScheduler / HTMX / Pico CSS / Cytoscape.js / Chart.js

## 项目结构

```
src/briefing/
  __main__.py              # 入口文件
  config.py                # Pydantic 配置模型
  database.py              # SQLAlchemy 引擎与会话管理
  models.py                # ORM 模型（6 张表）
  schemas.py               # Pydantic 数据模式（NewsItem、TickerQuote 等）
  scheduler.py             # APScheduler（每日简报 + 2 小时采集）
  settings_store.py        # 加密设置持久化

  collectors/              # 6 个数据源采集器
    base.py                # BaseCollector 接口 + RateLimiter
    yahoo.py               # Yahoo Finance（行情 + 新闻）
    googlenews.py          # Google News RSS
    rss.py                 # CNBC、MarketWatch、Reuters + 宏观过滤器
    newsapi.py             # NewsAPI（需密钥）
    alphavantage.py        # Alpha Vantage（需密钥）
    edgar.py               # SEC EDGAR 公告

  llm/                     # LLM 服务商
    base.py                # BaseLLMProvider 接口 + 工厂方法
    anthropic_provider.py  # Claude
    openai_provider.py     # GPT
    qwen_provider.py       # 通义千问（DashScope）
    ollama_provider.py     # 本地 Ollama
    prompts.py             # 聚类与中立化提示词

  pipeline/                # 简报生成管道
    orchestrator.py        # 主管道（run_briefing）
    news.py                # 去重、聚类、中立化
    market.py              # 行情数据聚合
    filings.py             # 公告摘要
    article_store.py       # 文章缓存（存储/检索/关联）

  delivery/                # 输出
    renderer.py            # HTML + Chart.js + 图谱数据渲染
    email.py               # SMTP 邮件推送

  web/                     # Web 界面
    app.py                 # FastAPI 应用工厂
    routes/                # 路由处理器
    templates/             # Jinja2 模板
    static/                # CSS 样式
```

## 开发指南

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/ -v

# 开发模式（自动重载）
python -m uvicorn briefing.web.app:create_app --factory --reload --app-dir src --port 8000
```

注意：开发模式（`--reload`）会跳过数据库初始化和定时任务。完整功能请使用 `python -m briefing`。

## 环境要求

- Python 3.12+
- 无需外部服务（使用 SQLite，无需 Redis/Celery）
- 可选：LLM API 密钥（用于新闻中立化处理）
- 可选：NewsAPI / Alpha Vantage 密钥（扩展新闻覆盖）
- 可选：SMTP 服务器（邮件推送）
- 可选：Docker（容器化部署）

## 许可证

私有项目。
