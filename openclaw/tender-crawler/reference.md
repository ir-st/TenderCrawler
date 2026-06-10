# TenderCrawler OpenClaw 技能参考

## 项目路径

技能包目录：`openclaw/tender-crawler/`  
定时入口：`scheduled_crawl.py`（项目根目录）

## 输出文件命名

| 前缀 | 场景 |
|------|------|
| `cron_{站点}_{时间}` | 定时任务 / OpenClaw |
| `web_{站点}_{时间}` | Web 控制台 |
| `tenders_{站点}_{时间}` | 命令行 `crawler.py` |

## 对比与招标时间

- 对比：`compare_{站点}_{时间}.json`（自动）
- 招标时间解析：Web 控制台「招标时间」标签；定时任务默认不跑详情解析（耗时长）

## openclaw.json 合并示例

将 `openclaw.config.example.json5` 中的 `skills.entries.tender-crawler` 合并到 `~/.openclaw/openclaw.json`。

注册 cron（在 OpenClaw 对话中让 Agent 执行，或 gateway API）：

```
cron.add < cron-job.example.json 的内容>
```

## 自定义站点或页数

```bash
export TENDER_CRAWLER_SITES=cebpub
export TENDER_CRAWLER_MAX_PAGES=5
python scheduled_crawl.py --json-summary
```
