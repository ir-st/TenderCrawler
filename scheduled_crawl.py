#!/usr/bin/env python3
"""定时抓取入口：依次爬取 cebpub / ccgp，保存 CSV/JSON 并生成对比报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from compare import compare_with_previous, format_compare_report, save_compare_json
from crawler import records_to_dicts, run_crawl, save_csv, save_json
from sites.registry import SITES, get_site


def _parse_sites(raw: str) -> list[str]:
    ids = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in ids if s not in SITES]
    if unknown:
        raise ValueError(f"未知站点: {', '.join(unknown)}")
    return ids or ["cebpub", "ccgp"]


def _site_types(site_id: str) -> list[str]:
    site = get_site(site_id)
    if site_id == "cebpub":
        return ["招标公告"]
    if site_id == "ccgp":
        return ["公开招标", "竞争性磋商", "竞争性谈判", "询价公告"]
    return list(site.business_types[:2])


def _site_keywords(site_id: str) -> list[str]:
    site = get_site(site_id)
    return list(dict.fromkeys([*site.default_keywords, *site.suggested_keywords[:6]]))


def crawl_site(
    site_id: str,
    *,
    output_dir: Path,
    max_pages: int | None,
    strict_filter: bool,
    prefix: str = "cron",
) -> dict:
    site = get_site(site_id)
    keywords = _site_keywords(site_id)
    business_types = _site_types(site_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    records = run_crawl(
        site_id=site_id,
        keywords=keywords,
        business_types=business_types,
        strict_filter=strict_filter,
        max_pages=max_pages,
        delay=site.default_delay if site_id == "ccgp" else max(site.default_delay, 0.8),
        log=lambda msg: print(f"[{site_id}] {msg}", file=sys.stderr),
    )

    base = output_dir / f"{prefix}_{site_id}_{stamp}"
    json_path = base.with_suffix(".json")
    save_json(records, json_path)
    save_csv(records, base.with_suffix(".csv"))

    compare_result = compare_with_previous(
        output_dir,
        site_id=site_id,
        current_records=records_to_dicts(records),
        current_json_path=json_path,
    )
    compare_path = output_dir / f"compare_{site_id}_{stamp}.json"
    save_compare_json(compare_result, compare_path)

    return {
        "site_id": site_id,
        "site_name": site.name,
        "total": len(records),
        "json_path": str(json_path),
        "csv_path": str(base.with_suffix(".csv")),
        "compare_path": str(compare_path),
        "compare": compare_result.summary(),
        "compare_report": format_compare_report(compare_result),
    }


def _default_max_pages() -> int | None:
    raw = os.environ.get("TENDER_CRAWLER_MAX_PAGES", "").strip()
    if not raw:
        return None
    n = int(raw)
    return n if n > 0 else None


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="TenderCrawler 定时抓取（cebpub + ccgp）")
    p.add_argument(
        "--sites",
        default=os.environ.get("TENDER_CRAWLER_SITES", "cebpub,ccgp"),
        help="逗号分隔站点 ID，默认 cebpub,ccgp",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("TENDER_CRAWLER_OUTPUT", "output")),
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=_default_max_pages(),
        help="每组合最多页数，省略则不限",
    )
    p.add_argument("--no-strict-filter", action="store_true")
    p.add_argument(
        "--prefix",
        default=os.environ.get("TENDER_CRAWLER_PREFIX", "cron"),
        help="输出文件名前缀，默认 cron",
    )
    p.add_argument(
        "--json-summary",
        action="store_true",
        help="最后一行输出 JSON 摘要（供 OpenClaw 解析）",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    site_ids = _parse_sites(args.sites)
    results: list[dict] = []
    exit_code = 0

    print(f"=== TenderCrawler 定时抓取 {datetime.now().isoformat(timespec='seconds')} ===")
    for site_id in site_ids:
        try:
            result = crawl_site(
                site_id,
                output_dir=args.output_dir,
                max_pages=args.max_pages,
                strict_filter=not args.no_strict_filter,
                prefix=args.prefix,
            )
            results.append(result)
            print()
            print(result["compare_report"])
        except Exception as exc:  # noqa: BLE001
            exit_code = 1
            err = {"site_id": site_id, "error": str(exc)}
            results.append(err)
            print(f"[{site_id}] 失败: {exc}", file=sys.stderr)

    summary = {
        "ok": exit_code == 0,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "sites": results,
    }
    if args.json_summary:
        print("\n__TENDER_CRAWLER_SUMMARY__=" + json.dumps(summary, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
