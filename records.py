"""招投标记录数据结构与标题分类。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TenderRecord:
    business_id: str
    title: str
    business_type: str
    search_keyword: str
    source_site: str = ""
    categories: list[str] = field(default_factory=list)
    region: str = ""
    industry: str = ""
    platform: str = ""
    publish_time: str = ""
    end_time: str = ""
    tender_project_code: str = ""
    transaction_platf_code: str = ""
    schema_version: str = ""
    portal_url: str = ""
    list_type: str = "0"
    row_guid: str = ""
    business_keyword: str = ""

    @property
    def dedupe_key(self) -> str:
        return f"{self.business_id}|{self.business_type}"


CATEGORY_PATTERNS: dict[str, re.Pattern[str]] = {
    "信息安全风险评估": re.compile(
        r"信息安全.*风险|安全风险.*评估|威胁.*风险.*评估|数据安全风险评估|"
        r"等级保护.*风险|网络安全.*风险.*评估",
        re.I,
    ),
    "商用密码评估": re.compile(
        r"商用密码|密码应用.*安全|密评|密码安全性评估",
        re.I,
    ),
    "渗透测试": re.compile(r"渗透测试|渗透\s*测|红队|攻防演练", re.I),
    "代码审计": re.compile(r"代码审计|源代码审计|源码审计|代码安全审计", re.I),
    "代码扫描": re.compile(r"代码扫描|源码扫描|静态代码|静态应用安全", re.I),
    "漏洞扫描": re.compile(r"漏洞扫描|漏洞检测|漏扫|脆弱性扫描", re.I),
}


def classify_title(title: str) -> list[str]:
    cats = []
    for name, pattern in CATEGORY_PATTERNS.items():
        if pattern.search(title):
            cats.append(name)
    return cats
