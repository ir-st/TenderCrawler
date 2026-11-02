"""中国政府采购网 search.ccgp.gov.cn/bxsearch 抓取。"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from records import TenderRecord, classify_title
from sites.registry import SiteConfig

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 公告类型 -> bidType 参数（参考采购网检索页）
BID_TYPE_CODE: dict[str, str] = {
    "全部": "0",
    "公开招标": "1",
    "询价公告": "2",
    "竞争性谈判": "3",
    "单一来源": "4",
    "资格预审": "5",
    "更正公告": "6",
    "竞争性磋商": "7",
    "中标公告": "8",
    "成交公告": "9",
    "终止公告": "10",
}

RATE_LIMIT_MARKERS = ("您的访问过于频繁", "频繁访问")
PAGE_SIZE = 20
DEFAULT_TIMEOUT = (15, 90)  # (连接超时秒, 读取超时秒)
MAX_RETRIES = 3
SEARCH_URLS = (
    "https://search.ccgp.gov.cn/bxsearch",
    "http://search.ccgp.gov.cn/bxsearch",
)


def _ccgp_date(value: str) -> str:
    """YYYY-MM-DD -> YYYY:MM:DD（采购网 timeType=6 格式）。"""
    if not value:
        return ""
    return value.strip().replace("-", ":")


def _default_date_range() -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=180)
    return (
        start.strftime("%Y:%m:%d"),
        end.strftime("%Y:%m:%d"),
    )


def _normalize_href(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin("https://www.ccgp.gov.cn", href)


def _parse_list_item(
    li,
    *,
    business_type: str,
    search_keyword: str,
    strict_filter: bool,
    portal_base: str,
    source_site: str,
) -> TenderRecord | None:
    anchor = li.select_one("a")
    if not anchor:
        return None
    title = anchor.get_text(strip=True)
    if not title:
        return None

    categories = classify_title(title)
    if strict_filter and not categories:
        return None

    detail_url = _normalize_href(anchor.get("href", ""))
    business_id = hashlib.md5(detail_url.encode("utf-8")).hexdigest() if detail_url else title

    publish_time = ""
    region = ""
    industry = ""
    buyer = ""
    agency = ""
    notice_subtype = ""

    for span in li.select("span"):
        parts = [p.strip() for p in span.get_text().split("|") if p.strip()]
        if not parts:
            continue
        if re.match(r"\d{4}[\.\-]\d", parts[0]):
            publish_time = parts[0].split()[0].replace(".", "-")
        for part in parts[1:]:
            if part.startswith("采购人"):
                buyer = part.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif part.startswith("代理机构"):
                agency = part.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif "公告" in part and len(part) < 20:
                notice_subtype = part
            elif not region and ("省" in part or "市" in part or "区" in part):
                region = part.replace("\r", "").strip()
        break

    platform = "中国政府采购网"
    if agency:
        platform = f"{platform} / {agency}"

    return TenderRecord(
        business_id=business_id,
        title=title,
        business_type=business_type,
        search_keyword=search_keyword,
        source_site=source_site,
        categories=categories or ["未分类"],
        region=region,
        industry=notice_subtype or industry,
        platform=platform,
        publish_time=publish_time,
        end_time="",
        tender_project_code="",
        transaction_platf_code=buyer,
        schema_version="",
        portal_url=detail_url or portal_base,
        list_type="direct",
        row_guid="",
        business_keyword="",
    )


class CcgpCrawler:
    def __init__(
        self,
        site: SiteConfig,
        *,
        page_size: int = PAGE_SIZE,
        delay_seconds: float = 3.0,
        timeout: int | tuple[int, int] = DEFAULT_TIMEOUT,
    ) -> None:
        self.site = site
        self.page_size = page_size
        self.delay_seconds = delay_seconds
        self.timeout = timeout if timeout else DEFAULT_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        self._warmed = False
        self._search_urls = list(SEARCH_URLS)
        if site.search_api and site.search_api not in self._search_urls:
            self._search_urls.insert(0, site.search_api)

    def _get_with_retry(self, params: dict) -> requests.Response:
        """带重试的 GET；采购网响应较慢，超时后自动换协议重试。"""
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            for base_url in self._search_urls:
                try:
                    resp = self.session.get(
                        base_url,
                        params=params,
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                    return resp
                except (requests.Timeout, requests.ConnectionError) as exc:
                    last_error = exc
                    time.sleep(min(2 * attempt, 8))
                except requests.RequestException as exc:
                    last_error = exc
                    time.sleep(2)
        hint = (
            "中国政府采购网连接超时或不可达。该站响应较慢，建议：\n"
            "1) 将请求间隔调至 4 秒以上；\n"
            "2) 减少关键词/业务类型或限制抓取页数；\n"
            "3) 稍后重试或检查本机网络/代理。"
        )
        raise RuntimeError(hint) from last_error

    def _warmup(self) -> None:
        if self._warmed:
            return
        try:
            self.session.get(
                "https://www.ccgp.gov.cn/",
                timeout=(10, 30),
            )
        except requests.RequestException:
            try:
                self.session.get("http://www.ccgp.gov.cn/", timeout=(10, 30))
            except requests.RequestException:
                pass
        time.sleep(1.0)
        self._warmed = True

    def _check_rate_limit(self, html: str) -> None:
        if any(m in html for m in RATE_LIMIT_MARKERS):
            raise RuntimeError(
                "中国政府采购网提示访问过于频繁，请增大请求间隔（建议 ≥3 秒）"
                "或稍后再试。详见 https://search.ccgp.gov.cn/bxsearch"
            )

    def fetch_page(
        self,
        *,
        keyword: str,
        business_type: str,
        page_no: int,
        date_start: str = "",
        date_stop: str = "",
    ) -> tuple[list, int]:
        self._warmup()
        start, end = _default_date_range()
        if date_start:
            start = _ccgp_date(date_start) or start
        if date_stop:
            end = _ccgp_date(date_stop) or end

        bid_type = BID_TYPE_CODE.get(business_type, "0")
        params = {
            "searchtype": "1",
            "page_index": str(page_no),
            "bidSort": "0",
            "buyerName": "",
            "projectId": "",
            "pinMu": "0",
            "bidType": bid_type,
            "dbselect": "bidx",
            "kw": keyword,
            "start_time": start,
            "end_time": end,
            "timeType": "6",
            "displayZone": "",
            "zoneId": "",
            "pppStatus": "0",
            "agentName": "",
        }
        resp = self._get_with_retry(params)
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        self._check_rate_limit(html)

        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".vT-srch-result-list-bid li")
        total_match = re.search(
            r"共\s*(\d+)\s*条",
            soup.get_text(" ", strip=True),
        )
        total = int(total_match.group(1)) if total_match else len(items)
        if not total_match and items:
            total = max(len(items), page_no * self.page_size)
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
    ) -> Iterable:
        page_no = 1
        total_pages = 1
        prev_last_title: str | None = None

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
            if not items:
                break
            last_a = items[-1].select_one("a")
            last_title = last_a.get_text(strip=True) if last_a else None
            if last_title and last_title == prev_last_title:
                break
            prev_last_title = last_title
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
                for li in self.fetch_all_for_query(
                    keyword=kw,
                    business_type=bt,
                    date_start=date_start,
                    date_stop=date_stop,
                    max_pages=max_pages,
                    on_progress=on_progress,
                ):
                    rec = _parse_list_item(
                        li,
                        business_type=bt,
                        search_keyword=kw,
                        strict_filter=strict_filter,
                        portal_base=self.site.portal_url,
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
