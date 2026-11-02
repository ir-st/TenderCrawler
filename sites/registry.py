"""可抓取目标站点注册表。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteConfig:
    id: str
    name: str
    description: str
    portal_url: str
    search_api: str
    default_keywords: tuple[str, ...]
    suggested_keywords: tuple[str, ...]
    business_types: tuple[str, ...]
    adapter: str = "cebpub"
    default_delay: float = 0.8
    enabled: bool = True


SHARED_KEYWORDS = (
    "信息安全风险评估",
    "商用密码评估",
    "商用密码应用安全性评估",
    "密码应用安全性评估",
    "数据安全风险评估",
    "网络安全等级保护测评",
    "密评",
    "渗透测试",
    "代码审计",
    "代码扫描",
    "漏洞扫描",
)


# 注意：必须使用 https。站点已将 http 301 重定向到 https，
# requests 跟随 301 时会把 POST 降级为 GET，导致查询参数丢失、返回 success:false。
CEBPUB_BASE = "https://www.cebpubservice.com/ctpsp_iiss"

SITES: dict[str, SiteConfig] = {
    "cebpub": SiteConfig(
        id="cebpub",
        name="中国招标投标公共服务平台",
        description=(
            "信息公开 JSON 接口（getStringMethod.do）；"
            "业务类型：招标公告、开标记录、评标公示、中标公告；"
            "默认间隔 0.8 秒；详情经加密中转页打开；"
            "支持结果对比与招标时间解析"
        ),
        portal_url=f"{CEBPUB_BASE}/searchbusinesstypebeforedooraction/getSearch.do",
        search_api=f"{CEBPUB_BASE}/searchbusinesstypebeforedooraction/getStringMethod.do",
        default_keywords=(
            "信息安全风险评估",
            "商用密码评估",
        ),
        suggested_keywords=SHARED_KEYWORDS,
        business_types=("招标公告", "开标记录", "评标公示", "中标公告"),
        adapter="cebpub",
        default_delay=0.8,
    ),
    "ccgp": SiteConfig(
        id="ccgp",
        name="中国政府采购网",
        description=(
            "HTML 列表检索（search.ccgp.gov.cn/bxsearch）；"
            "业务类型：全部、公开招标、询价公告等；"
            "响应慢、易限流，建议间隔 ≥4 秒；详情页直链；"
            "支持结果对比与招标时间解析"
        ),
        portal_url="https://search.ccgp.gov.cn/bxsearch",
        search_api="https://search.ccgp.gov.cn/bxsearch",
        default_keywords=(
            "信息安全风险评估",
            "商用密码评估",
            "渗透测试",
        ),
        suggested_keywords=SHARED_KEYWORDS,
        business_types=(
            "全部",
            "公开招标",
            "询价公告",
            "竞争性谈判",
            "竞争性磋商",
            "更正公告",
            "中标公告",
        ),
        adapter="ccgp",
        default_delay=3.0,
    ),
}


def list_sites(*, enabled_only: bool = True) -> list[SiteConfig]:
    sites = list(SITES.values())
    if enabled_only:
        sites = [s for s in sites if s.enabled]
    return sites


def get_site(site_id: str) -> SiteConfig:
    if site_id not in SITES:
        raise KeyError(f"未知站点: {site_id}")
    site = SITES[site_id]
    if not site.enabled:
        raise KeyError(f"站点未启用: {site_id}")
    return site
