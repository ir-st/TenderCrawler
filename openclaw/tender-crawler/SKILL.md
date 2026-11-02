---
name: tender-crawler
description: >-
  Runs TenderCrawler daily tender/bid crawls for cebpub and ccgp (China public
  procurement sites), saves CSV/JSON, compares with previous snapshots, and
  reports new/removed notices. Use when scheduling daily noon China-time crawls,
  OpenClaw cron jobs, tender-crawler automation, or 招投标定时抓取.
metadata: {"openclaw":{"emoji":"📋","homepage":"https://github.com","requires":{"bins":["python"],"env":["TENDER_CRAWLER_HOME"]}}}
---

# TenderCrawler 定时抓取

对中国招标投标公共服务平台（`cebpub`）与中国政府采购网（`ccgp`）做关键词抓取，保存结果并与上次快照对比。

## 前置条件

1. 本机已克隆 TenderCrawler 项目并安装依赖：

```bash
cd {TENDER_CRAWLER_HOME}
python -m pip install -r requirements.txt
```

2. 环境变量（OpenClaw `skills.entries` 或 `.env` 中配置）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `TENDER_CRAWLER_HOME` | 项目根目录（必填） | `C:/Users/me/TenderCrawler` |
| `TENDER_CRAWLER_OUTPUT` | 输出目录 | `{TENDER_CRAWLER_HOME}/output` |
| `TENDER_CRAWLER_SITES` | 站点列表 | `cebpub,ccgp` |
| `TENDER_CRAWLER_MAX_PAGES` | 每组合最多页数（建议定时任务设 2–5） | `3` |

`{baseDir}` 为本技能目录；`{TENDER_CRAWLER_HOME}` 为上述环境变量。

## 手动执行（立即抓取）

**Linux / macOS / OpenClaw 容器：**

```bash
cd "$TENDER_CRAWLER_HOME"
python scheduled_crawl.py --max-pages 3 --json-summary
```

**Windows：**

```bat
cd /d %TENDER_CRAWLER_HOME%
python scheduled_crawl.py --max-pages 3 --json-summary
```

或使用技能脚本：

```bash
python {baseDir}/scripts/run_daily_crawl.py
```

输出在 `output/`，文件名前缀 `cron_{站点}_{时间}`，并生成 `compare_{站点}_{时间}.json`。

## 每日 12:00（北京时间）定时任务

使用 OpenClaw **cron** 工具注册任务。表达式 `0 12 * * *`，时区 **`Asia/Shanghai`**。

### 方式 A：OpenClaw cron（推荐）

调用 `cron.add`，粘贴 `cron-job.example.json`（位于 `{baseDir}/`）内容，或等价配置：

- **name**: `tender-crawler-daily-noon`
- **schedule**: `0 12 * * *`，`tz`: `Asia/Shanghai`
- **sessionTarget**: `isolated`
- **payload.kind**: `agentTurn`
- **message**: 见 `{baseDir}/cron-job.example.json`

任务触发后 Agent 应：

1. 确认 `TENDER_CRAWLER_HOME` 已设置且依赖已安装
2. 执行 `{baseDir}/scripts/run_daily_crawl.py`（或 `scheduled_crawl.py`）
3. 读取 stdout 中 `__TENDER_CRAWLER_SUMMARY__=` 后的 JSON
4. 用中文汇总：各站点条数、新增/消失数量、失败原因（如有）
5. 若有配置 `delivery`，将摘要推送到 IM 频道

安装后验证：

```bash
cron.list
```

### 方式 B：系统 cron / 计划任务

**Linux crontab**（在 `TENDER_CRAWLER_HOME` 下执行）：

```cron
0 12 * * * TENDER_CRAWLER_HOME=/path/to/TenderCrawler TENDER_CRAWLER_MAX_PAGES=3 /usr/bin/python3 /path/to/TenderCrawler/scheduled_crawl.py >> /path/to/TenderCrawler/output/cron.log 2>&1
```

**Windows 任务计划程序**：每天 12:00 运行 `{baseDir}/scripts/run_daily_crawl.bat`。

## 安装本技能

在 OpenClaw 工作区：

```bash
# 安装到当前 workspace（仅当前 Agent）
openclaw skills install /path/to/TenderCrawler/openclaw/tender-crawler

# 或安装到全局（定时 isolated 会话更易加载）
openclaw skills install /path/to/TenderCrawler/openclaw/tender-crawler --global
```

在 `openclaw.json` 中启用并注入环境变量，示例见 `{baseDir}/openclaw.config.example.json5`。

## 抓取范围（默认定时任务）

| 站点 | 业务类型 | 间隔 |
|------|----------|------|
| cebpub | 招标公告 | 0.8s |
| ccgp | 公开招标、竞争性磋商、竞争性谈判、询价公告 | 3s（建议 max-pages 限制） |

关键词来自 `sites/registry.py` 默认词 + 部分推荐词。详情见 [reference.md](reference.md)。

## 故障排查

- **ccgp 超时/0 条**：增大间隔、`--max-pages 2`，或减少关键词（改 `scheduled_crawl.py` 或环境变量）
- **isolated cron 找不到技能**：使用 `openclaw skills install --global`
- **Python 找不到模块**：必须在 `TENDER_CRAWLER_HOME` 下执行，且已 `pip install -r requirements.txt`
