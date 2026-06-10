"""招标公告详情：抓取招标文件获取时间与投标/递交截止时间。"""

from __future__ import annotations

import html
import re
import time
from typing import Callable

import requests
from bs4 import BeautifulSoup

from detail import business_keyword_for

CEBPUB_FIND_DETAIL = (
    "http://www.cebpubservice.com/ctpsp_iiss/SecondaryAction/findDetail.do"
)
CEBPUB_PORTAL = (
    "http://www.cebpubservice.com/ctpsp_iiss/"
    "searchbusinesstypebeforedooraction/getSearch.do"
)
CEBPUB_SHOW_DETAILS = (
    "http://www.cebpubservice.com/ctpsp_iiss/"
    "searchbusinesstypebeforedooraction/showDetails.do"
)

TENDER_ANNOUNCEMENT_TYPES = frozenset(
    {
        "招标公告",
        "公开招标",
        "询价公告",
        "竞争性谈判",
        "竞争性磋商",
        "全部",
    }
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DATE_TIME_FRAGMENT = (
    r"\d{4}年\d{1,2}月\d{1,2}日"
    r"(?:\d{1,2}[:：时]\d{1,2}[:：分](?:\d{1,2}秒)?)?"
)
DATE_RANGE = rf"({DATE_TIME_FRAGMENT}\s*至\s*{DATE_TIME_FRAGMENT})"

DOC_GET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"文件发售时间[：:\s]*【([^】]+)】", re.I),
    re.compile(rf"获取招标文件[^。]{{0,40}}?【([^】]+)】", re.I),
    re.compile(rf"招标文件[^。]{{0,40}}?(?:获取|发售)[^。]{{0,30}}?时间[：:\s]*【([^】]+)】", re.I),
    re.compile(rf"文件(?:获取|发售)[^。]{{0,20}}?时间[：:\s]*({DATE_RANGE}[^。]{{0,20}})", re.I),
    re.compile(
        r"获取招标文件[^。\n]{0,30}?时间[：:\s]*([^\n。；;]{6,120})",
        re.I,
    ),
]

BID_SUBMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"递交截止时间[：:\s]*({DATE_TIME_FRAGMENT})", re.I),
    re.compile(rf"投标(?:文件)?(?:递交)?截止时间[：:\s]*({DATE_TIME_FRAGMENT})", re.I),
    re.compile(rf"提交投标文件截止时间[：:\s]*({DATE_TIME_FRAGMENT})", re.I),
    re.compile(rf"投标截止时间[：:\s]*({DATE_TIME_FRAGMENT})", re.I),
    re.compile(
        rf"({DATE_TIME_FRAGMENT}[^。\n]{{0,20}}?前)递交投标文件",
        re.I,
    ),
    re.compile(
        r"获取招标文件[^。\n]{0,60}?(\d{4}年\d{1,2}月\d{1,2}日[^。\n]{0,40}?前)递交",
        re.I,
    ),
]


def is_tender_announcement(business_type: str) -> bool:
    bt = (business_type or "").strip()
    if bt in TENDER_ANNOUNCEMENT_TYPES:
        return True
    return "招标公告" in bt or bt.endswith("公告") and "中标" not in bt and "更正" not in bt


def html_to_text(content: str) -> str:
    raw = html.unescape(content or "")
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator="", strip=False)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_extracted(value: str) -> str:
    value = html.unescape(value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip("：:，,；;。.")
    if len(value) > 160:
        value = value[:160] + "…"
    return value


def extract_doc_get_time(text: str) -> str:
    for pattern in DOC_GET_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_extracted(match.group(1))
    return ""


def extract_bid_submit_time(text: str) -> str:
    for pattern in BID_SUBMIT_PATTERNS:
        match = pattern.search(text)
        if match:
            val = _clean_extracted(match.group(1))
            dt = re.search(DATE_TIME_FRAGMENT, val)
            if dt:
                return dt.group(0)
            return val
    return ""


def parse_bulletin_times(text: str) -> dict[str, str]:
    plain = html_to_text(text) if "<" in text else text
    return {
        "doc_get_time": extract_doc_get_time(plain),
        "bid_submit_time": extract_bid_submit_time(plain),
    }


class BulletinDetailFetcher:
    def __init__(self, *, delay_seconds: float = 0.5, timeout: int = 30) -> None:
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        self._cebpub_ready = False

    def _sleep(self) -> None:
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

    def _ensure_cebpub(self) -> None:
        if self._cebpub_ready:
            return
        self.session.get(CEBPUB_PORTAL, timeout=self.timeout)
        self._cebpub_ready = True

    def fetch_cebpub_text(self, rec: dict) -> str:
        self._ensure_cebpub()
        payload = {
            "schemaVersion": rec.get("schema_version") or "",
            "businessKeyWord": rec.get("business_keyword")
            or business_keyword_for(rec.get("business_type") or ""),
            "tenderProjectCode": rec.get("tender_project_code") or "",
            "businessObjectName": rec.get("title") or "",
            "businessId": rec.get("business_id") or "",
        }
        headers = {
            "Referer": CEBPUB_SHOW_DETAILS,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = self.session.post(
            CEBPUB_FIND_DETAIL,
            data=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(body.get("message") or "平台返回失败")
        obj = body.get("object") or {}
        bulletins = obj.get("tenderBulletin") or obj.get("amendBulletin") or []
        if not bulletins:
            for key in ("qualifyBulletin", "amendBulletin"):
                bulletins = obj.get(key) or []
                if bulletins:
                    break
        if not bulletins:
            raise RuntimeError("未找到招标公告正文")
        content = bulletins[0].get("bulletinContent") or ""
        if not content:
            raise RuntimeError("公告正文为空")
        return content

    def fetch_ccgp_text(self, rec: dict) -> str:
        url = (rec.get("portal_url") or "").strip()
        if not url.startswith("http"):
            raise RuntimeError("无有效详情链接")
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        block = (
            soup.select_one(".vF_detail_content")
            or soup.select_one("#detailContent")
            or soup.select_one("blockquote")
        )
        if block:
            return block.get_text(separator="", strip=False)
        return soup.get_text(separator="", strip=False)

    def fetch_record(self, rec: dict) -> dict[str, str]:
        source_site = (rec.get("source_site") or "cebpub").strip()
        if source_site == "ccgp":
            text = self.fetch_ccgp_text(rec)
        else:
            text = self.fetch_cebpub_text(rec)
        return parse_bulletin_times(text)


def enrich_tender_announcements(
    records: list[dict],
    *,
    delay_seconds: float = 0.5,
    on_progress: Callable[[int, int, dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict]:
    """为招标类公告补充 doc_get_time / bid_submit_time。"""
    fetcher = BulletinDetailFetcher(delay_seconds=delay_seconds)
    targets = [
        (idx, rec)
        for idx, rec in enumerate(records)
        if is_tender_announcement(rec.get("business_type") or "")
    ]
    total = len(targets)
    results: list[dict] = []

    for n, (idx, rec) in enumerate(targets, start=1):
        if should_stop and should_stop():
            break
        row = {
            "index": idx,
            "title": rec.get("title") or "",
            "business_type": rec.get("business_type") or "",
            "region": rec.get("region") or "",
            "platform": rec.get("platform") or "",
            "publish_time": rec.get("publish_time") or "",
            "end_time": rec.get("end_time") or "",
            "doc_get_time": "",
            "bid_submit_time": "",
            "status": "pending",
            "error": "",
        }
        try:
            times = fetcher.fetch_record(rec)
            row["doc_get_time"] = times.get("doc_get_time") or ""
            row["bid_submit_time"] = times.get("bid_submit_time") or ""
            if not row["doc_get_time"] and not row["bid_submit_time"]:
                row["status"] = "empty"
                row["error"] = "正文中未识别到时间字段"
            else:
                row["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            row["status"] = "failed"
            row["error"] = str(exc)
        results.append(row)
        if on_progress:
            on_progress(n, total, row)
        fetcher._sleep()

    return results
