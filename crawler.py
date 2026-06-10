#!/usr/bin/env python3
"""
招投标信息抓取核心模块。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

from compare import compare_with_previous, format_compare_report, save_compare_json
from detail import business_keyword_for
from http_utils import parse_json_response
from records import TenderRecord, classify_title
from sites.registry import SiteConfig, get_site

DEFAULT_KEYWORDS = list(get_site("cebpub").default_keywords)
BUSINESS_TYPES = list(get_site("cebpub").business_types)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def parse_item(
    raw: dict,
    *,
    business_type: str,
    search_keyword: str,
    strict_filter: bool,
    portal_url: str,
    source_site: str,
) -> TenderRecord | None:
    title = (raw.get("businessObjectName") or "").strip()
    if not title:
        return None

    categories = classify_title(title)
    if strict_filter and not categories:
        return None

    publish = raw.get("receiveTime") or ""
    if publish == "1970-01-01":
        publish = ""
    end = raw.get("bulletinEndTime") or ""
    if end == "1970-01-01":
        end = ""

    return TenderRecord(
        business_id=str(raw.get("businessId") or ""),
        title=title,
        business_type=business_type,
        search_keyword=search_keyword,
        source_site=source_site,
        categories=categories or ["未分类"],
        region=(raw.get("regionName") or "").strip(),
        industry=(raw.get("industriesType") or "").strip(),
        platform=(raw.get("transactionPlatfName") or "").strip(),
        publish_time=publish,
        end_time=end,
        tender_project_code=str(raw.get("tenderProjectCode") or ""),
        transaction_platf_code=str(raw.get("transactionPlatfCode") or ""),
        schema_version=str(raw.get("schemaVersion") or ""),
        portal_url=portal_url,
        list_type=str(raw.get("type") or "0"),
        row_guid=str(raw.get("rowGuid") or ""),
        business_keyword=business_keyword_for(business_type),
    )


class CebpubCrawler:
    def __init__(
        self,
        site: SiteConfig,
        *,
        page_size: int = 50,
        delay_seconds: float = 0.8,
        timeout: int = 30,
    ) -> None:
        self.site = site
        self.page_size = page_size
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Referer": site.portal_url,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
        )
        self.timeout = timeout
        self._warmed = False

    def _warmup(self) -> None:
        if self._warmed:
            return
        try:
            self.session.get(self.site.portal_url, timeout=self.timeout)
            time.sleep(0.5)
        except requests.RequestException:
            pass
        self._warmed = True

    def fetch_page(
        self,
        *,
        keyword: str,
        business_type: str,
        page_no: int,
        date_start: str = "",
        date_stop: str = "",
    ) -> tuple[list[dict], int]:
        payload = {
            "searchName": keyword,
            "searchArea": "",
            "searchIndustry": "",
            "centerPlat": "",
            "businessType": business_type,
            "searchTimeStart": date_start,
            "searchTimeStop": date_stop,
            "timeTypeParam": "",
            "bulletinIssnTime": "",
            "bulletinIssnTimeStart": "",
            "bulletinIssnTimeStop": "",
            "pageNo": page_no,
            "row": self.page_size,
        }
        self._warmup()
        resp = self.session.post(
            self.site.search_api, data=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        body = parse_json_response(
            resp, source="中国招标投标公共服务平台"
        )
        if not body.get("success"):
            msg = body.get("message") or "未知错误"
            raise RuntimeError(
                f"招标投标平台查询失败: keyword={keyword!r} type={business_type!r} "
                f"page={page_no}；{msg}（请确认业务类型与该站点匹配，如「招标公告」而非「全部」）"
            )
        if body.get("object") is None:
            raise RuntimeError(
                f"招标投标平台无数据: keyword={keyword!r} type={business_type!r} "
                f"page={page_no}（业务类型「{business_type}」可能无效）"
            )
        obj = body.get("object") or {}
        items = obj.get("returnlist") or []
        page = obj.get("page") or {}
        total = int(page.get("totalCount") or 0)
        return items, total

    def fetch_all_for_query(
        self,
        *,
        keyword: str,
        business_type: str,
        date_start: str = "",
        date_stop: str = "",
        max_pages: int | None = None,
        on_progress: callable | None = None,
    ) -> Iterable[dict]:
        page_no = 1
        total_pages = 1
        while page_no <= total_pages:
            if max_pages is not None and page_no > max_pages:
                break
            items, total = self.fetch_page(
                keyword=keyword,
                business_type=business_type,
                page_no=page_no,
                date_start=date_start,
                date_stop=date_stop,
            )
            total_pages = max(1, (total + self.page_size - 1) // self.page_size)
            if on_progress:
                on_progress(
                    keyword=keyword,
                    business_type=business_type,
                    page=page_no,
                    total_pages=total_pages,
                    total_count=total,
                )
            yield from items
            if page_no >= total_pages:
                break
            page_no += 1
            time.sleep(self.delay_seconds)

    def crawl(
        self,
        keywords: list[str],
        business_types: list[str],
        *,
        strict_filter: bool = True,
        date_start: str = "",
        date_stop: str = "",
        max_pages: int | None = None,
        on_progress: callable | None = None,
        log: callable = print,
    ) -> list[TenderRecord]:
        seen: set[str] = set()
        records: list[TenderRecord] = []

        for kw in keywords:
            for bt in business_types:
                log(f"正在抓取: 关键词={kw!r} 类型={bt}")
                for raw in self.fetch_all_for_query(
                    keyword=kw,
                    business_type=bt,
                    date_start=date_start,
                    date_stop=date_stop,
                    max_pages=max_pages,
                    on_progress=on_progress,
                ):
                    rec = parse_item(
                        raw,
                        business_type=bt,
                        search_keyword=kw,
                        strict_filter=strict_filter,
                        portal_url=self.site.portal_url,
                        source_site=self.site.id,
                    )
                    if rec is None:
                        continue
                    if rec.dedupe_key in seen:
                        continue
                    seen.add(rec.dedupe_key)
                    records.append(rec)
                time.sleep(self.delay_seconds)

        records.sort(
            key=lambda r: (r.publish_time or "", r.title),
            reverse=True,
        )
        return records


def create_crawler(site_id: str, **kwargs):
    site = get_site(site_id)
    delay = kwargs.pop("delay_seconds", None)
    if delay is None:
        delay = site.default_delay
    kwargs.setdefault("delay_seconds", delay)

    if site.adapter == "ccgp":
        from sites.ccgp_crawler import CcgpCrawler, DEFAULT_TIMEOUT

        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        kwargs.setdefault("delay_seconds", site.default_delay)
        return CcgpCrawler(site, **kwargs)
    return CebpubCrawler(site, **kwargs)


def normalize_business_types(site_id: str, business_types: list[str]) -> list[str]:
    """仅保留当前站点支持的业务类型，避免混用另一站点的选项。"""
    site = get_site(site_id)
    allowed = set(site.business_types)
    picked = [t for t in business_types if t in allowed]
    if picked:
        return picked
    raise ValueError(
        f"所选业务类型不适用于「{site.name}」。"
        f"请选择：{', '.join(site.business_types)}"
    )


def run_crawl(
    *,
    site_id: str,
    keywords: list[str],
    business_types: list[str],
    strict_filter: bool = True,
    date_start: str = "",
    date_stop: str = "",
    max_pages: int | None = None,
    page_size: int = 50,
    delay: float = 0,
    on_progress: callable | None = None,
    log: callable | None = None,
) -> list[TenderRecord]:
    business_types = normalize_business_types(site_id, business_types)
    crawler_kwargs: dict = {"page_size": page_size}
    if delay > 0:
        crawler_kwargs["delay_seconds"] = delay
    crawler = create_crawler(site_id, **crawler_kwargs)
    return crawler.crawl(
        keywords=keywords,
        business_types=business_types,
        strict_filter=strict_filter,
        date_start=date_start,
        date_stop=date_stop,
        max_pages=max_pages,
        on_progress=on_progress,
        log=log or (lambda _msg: None),
    )


def records_to_dicts(records: list[TenderRecord]) -> list[dict]:
    rows = []
    for r in records:
        d = asdict(r)
        d["categories"] = r.categories
        rows.append(d)
    return rows


def save_json(records: list[TenderRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records_to_dicts(records), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_csv(records: list[TenderRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "title",
        "categories",
        "source_site",
        "business_type",
        "search_keyword",
        "region",
        "industry",
        "platform",
        "publish_time",
        "end_time",
        "tender_project_code",
        "business_id",
        "transaction_platf_code",
        "schema_version",
        "portal_url",
        "list_type",
        "row_guid",
        "business_keyword",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            row = asdict(r)
            row["categories"] = "|".join(r.categories)
            writer.writerow({k: row[k] for k in fields})


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="招投标信息抓取工具")
    p.add_argument("--site", default="cebpub", help="目标站点 ID")
    p.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS)
    p.add_argument("--types", nargs="+", choices=BUSINESS_TYPES, default=BUSINESS_TYPES)
    p.add_argument("--date-start", default="")
    p.add_argument("--date-stop", default="")
    p.add_argument("--no-strict-filter", action="store_true")
    p.add_argument("--page-size", type=int, default=50)
    p.add_argument("--delay", type=float, default=0.8)
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("-o", "--output-dir", type=Path, default=Path("output"))
    p.add_argument("--format", choices=("json", "csv", "both"), default="both")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        records = run_crawl(
            site_id=args.site,
            keywords=args.keywords,
            business_types=args.types,
            strict_filter=not args.no_strict_filter,
            date_start=args.date_start,
            date_stop=args.date_stop,
            max_pages=args.max_pages,
            page_size=args.page_size,
            delay=args.delay,
            log=lambda msg: print(msg, file=sys.stderr),
        )
    except (requests.RequestException, KeyError) as exc:
        print(f"失败: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = args.output_dir / f"tenders_{args.site}_{stamp}"
    json_path = base.with_suffix(".json")
    if args.format in ("json", "both"):
        save_json(records, json_path)
        print(f"已写入 JSON: {json_path}")
    if args.format in ("csv", "both"):
        save_csv(records, base.with_suffix(".csv"))
        print(f"已写入 CSV: {base.with_suffix('.csv')}")

    if args.format in ("json", "both") and json_path.is_file():
        compare_result = compare_with_previous(
            args.output_dir,
            site_id=args.site,
            current_json_path=json_path,
        )
        compare_path = args.output_dir / f"compare_{args.site}_{stamp}.json"
        save_compare_json(compare_result, compare_path)
        print(f"已写入对比: {compare_path}")
        print()
        print(format_compare_report(compare_result))

    print(f"\n共 {len(records)} 条（去重后）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
