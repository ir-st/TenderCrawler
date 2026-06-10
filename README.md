# TenderCrawler

招投标信息抓取、对比与招标时间解析工具。支持 **Web 控制台**、**命令行** 与 **Windows 一键启动**（`start.bat`）。

当前内置两个站点：**中国招标投标公共服务平台**（`cebpub`）、**中国政府采购网**（`ccgp`）。可按关键词检索公告，导出 CSV/JSON，自动与上一次同站点结果对比，并解析招标公告中的文件获取时间与投标截止时间。

## 支持站点

| 项目 | `cebpub` | `ccgp` |
|------|----------|--------|
| 名称 | 中国招标投标公共服务平台 | 中国政府采购网 |
| 门户 | [信息公开栏目](http://www.cebpubservice.com/ctpsp_iiss/searchbusinesstypebeforedooraction/getSearch.do) | [bxsearch](https://search.ccgp.gov.cn/bxsearch) |
| 数据方式 | JSON API（`getStringMethod.do`） | HTML 列表解析 |
| 业务类型 | 招标公告、开标记录、评标公示、中标公告 | 全部、公开招标、询价公告、竞争性谈判、竞争性磋商、更正公告、中标公告 |
| 默认间隔 | 0.8 秒 | 3 秒（界面建议 ≥4 秒） |
| 详情打开 | `/detail/open` 加密中转页 | 公告直链 |
| 招标时间解析 | `findDetail.do` 公告正文 | 详情页 HTML 正文 |
| 列表字段 | 含公告发布时间、公告结束时间 | 含公告发布时间（结束时间视页面而定） |

更多站点可在 `sites/registry.py` 注册扩展。

## 推荐关键词

内置 11 个推荐词（界面勾选或命令行传入）：

- 信息安全风险评估、商用密码评估、商用密码应用安全性评估
- 密码应用安全性评估、数据安全风险评估、网络安全等级保护测评、密评
- 渗透测试、代码审计、代码扫描、漏洞扫描

默认开启**标题二次过滤**，仅保留与上述安全/密评相关分类匹配的标题；可用 `--no-strict-filter` 关闭。

## 环境

- Python 3.10+
- 依赖：`requests`、`flask`、`beautifulsoup4`（见 `requirements.txt`）

```bash
pip install -r requirements.txt
```

## 启动方式

### Windows 一键启动（推荐）

双击项目根目录 `start.bat`（内部调用 `scripts/start.ps1`，已处理中文 Windows 控制台乱码）：

1. 检测 Python 3.10+
2. 安装 `requirements.txt` 依赖
3. 创建 `output/` 目录
4. 释放 5000 端口并启动 Web 服务
5. 自动打开浏览器 http://127.0.0.1:5000

关闭命令行窗口即停止服务。

### 手动启动

```bash
python -m pip install -r requirements.txt
python app.py
```

## Web 控制台

浏览器打开 http://127.0.0.1:5000 ，可：

- 选择目标网站（cebpub / ccgp）、关键词、业务类型（全选/取消全选）
- 设置日期范围、请求间隔、最多页数
- 查看实时进度与结果表格；标题跳转公告详情
- 下载 CSV / JSON

结果区三个标签页：

| 标签 | 说明 |
|------|------|
| **全部结果** | 抓取列表，含公告发布时间、公告结束时间 |
| **对比分析** | 与同站点上一次快照对比，展示新增/消失/未变 |
| **招标时间** | 自动解析招标类公告的**招标文件获取时间**、**投标/递交截止时间** |

抓取完成后会自动：保存快照 → 生成对比报告 → 后台解析招标时间（可「重新抓取招标时间」）。

## 命令行

```bash
# 默认 cebpub：多组关键词 × 四类业务，输出 CSV + JSON，并自动对比
python crawler.py

# 仅抓招标公告，限制日期
python crawler.py --types 招标公告 --date-start 2026-01-01

# 中国政府采购网（建议 --delay 4 以上）
python crawler.py --site ccgp --keywords 商用密码评估 --types 公开招标 --delay 4 --max-pages 2

# 自定义关键词、调试（每组合最多 1 页）
python crawler.py --keywords 商用密码评估 渗透测试 --max-pages 1

# 关闭标题二次过滤
python crawler.py --no-strict-filter

# 仅输出 JSON
python crawler.py --format json
```

## 输出文件

结果保存在 `output/` 目录：

| 文件 | 来源 | 示例 |
|------|------|------|
| `web_{站点}_{时间}.json/.csv` | Web 控制台 | `web_cebpub_20260605_115135.json` |
| `tenders_{站点}_{时间}.json/.csv` | 命令行 | `tenders_cebpub_20260602_092015.json` |
| `compare_{站点}_{时间}.json` | 自动对比 | `compare_cebpub_20260605_115135.json` |
| `bulletin_{站点}_{时间}.json` | 招标时间解析 | `bulletin_cebpub_20260605_190041.json` |

## 结果对比

逻辑见 `compare.py`：

1. 在 `output/` 查找**同一站点**、时间戳**紧邻上一次**的 JSON 快照。
2. 以 `business_id + 业务类型` 匹配（无 ID 时回退 URL 或标题）。
3. 首次抓取某站点无历史快照，不生成有效 diff。

```python
from pathlib import Path
from compare import compare_with_previous, format_compare_report

result = compare_with_previous(
    Path("output"),
    site_id="cebpub",
    current_json_path=Path("output/web_cebpub_20260605_115135.json"),
)
print(format_compare_report(result))
```

## 招标时间解析

逻辑见 `bulletin_detail.py`，针对招标类公告（如「招标公告」「公开招标」「竞争性磋商」等）：

| 站点 | 数据来源 | 提取字段 |
|------|----------|----------|
| cebpub | `SecondaryAction/findDetail.do` | 文件发售/获取时间、递交截止时间 |
| ccgp | 公告详情页 HTML | 获取招标文件时间、投标截止时间 |

正文格式因平台/项目而异，部分公告可能显示「未识别」，可手动「重新抓取招标时间」。

## 抓取逻辑

**cebpub**

1. 关键词 × 业务类型调用 `getStringMethod.do` 并翻页。
2. 按 `businessId + businessType` 去重。
3. 列表含 `receiveTime`（公告发布时间）、`bulletinEndTime`（公告结束时间）。

**ccgp**

1. 解析 `.vT-srch-result-list-bid` 列表，按关键词与类型检索。
2. 详情 URL 写入 `portal_url`，标题直链打开。
3. 默认超时较长，HTTPS 优先，内置重试。

## 项目结构

```
TenderCrawler/
├── app.py              # Flask Web 服务
├── crawler.py          # 爬虫入口与 CLI
├── compare.py          # 快照对比
├── bulletin_detail.py  # 招标公告时间解析
├── records.py          # 记录结构与标题分类
├── detail.py           # cebpub 详情页参数
├── http_utils.py       # JSON 响应解析
├── start.bat           # Windows 一键启动 Web
├── scheduled_crawl.py  # OpenClaw / cron 定时抓取入口
├── openclaw/
│   ├── install-skill.bat
│   └── tender-crawler/ # OpenClaw 技能包（SKILL.md + cron 示例）
├── sites/
│   ├── registry.py     # 站点注册（cebpub / ccgp）
│   └── ccgp_crawler.py
├── templates/          # Web 页面
└── output/             # 抓取结果（git 忽略）
```

## 说明

- 请合理设置请求间隔，**ccgp 建议 ≥4 秒**，避免限流或超时。
- 导出含 `business_id`、`tender_project_code`、`portal_url`、`publish_time`、`end_time` 等字段。
- 仅供个人学习与信息汇总，请遵守各平台使用条款与相关法律法规。

## OpenClaw 技能包（每日 12:00 定时抓取）

技能目录：`openclaw/tender-crawler/`

```bash
# 安装技能（推荐全局，便于 isolated cron 加载）
openclaw skills install ./openclaw/tender-crawler --global

# Windows 一键安装引导
openclaw\install-skill.bat
```

在 `~/.openclaw/openclaw.json` 合并 `openclaw/tender-crawler/openclaw.config.example.json5`，设置 `TENDER_CRAWLER_HOME` 为本项目路径。

**注册每天北京时间 12:00 定时任务**：让 OpenClaw Agent 执行 `cron.add`，配置见 `openclaw/tender-crawler/cron-job.example.json`（`0 12 * * *`，`tz: Asia/Shanghai`）。

**手动测试定时抓取：**

```bash
python scheduled_crawl.py --max-pages 3 --json-summary
# 或
python openclaw/tender-crawler/scripts/run_daily_crawl.py
```

定时任务依次抓取 **cebpub + ccgp**，输出 `cron_{站点}_{时间}.csv/json` 及对比报告。详见技能内 `SKILL.md`。
