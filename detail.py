"""招投标详情页跳转（中国招标投标公共服务平台）。"""

from __future__ import annotations

CEBPUB_DETAIL_ACTION = (
    "http://www.cebpubservice.com/ctpsp_iiss/"
    "searchbusinesstypebeforedooraction/showDetails.do"
)
CEBPUB_FRAME_DETAIL = (
    "http://connect.cebpubservice.com/PSPFrame/infobasemis/socialpublic/"
    "publicyewu/Frame_yewuDetail?rowguid="
)

# 与官网 jiaoyigongkai.js 中 showDetails 的 businessKeyWord 一致
BUSINESS_TYPE_KEYWORD: dict[str, str] = {
    "招标项目": "tenderProject",
    "招标公告": "tenderBulletin",
    "开标记录": "openBidRecord",
    "评标公示": "winCandidateBulletin",
    "中标公告": "winBidBulletin",
}


def business_keyword_for(business_type: str) -> str:
    return BUSINESS_TYPE_KEYWORD.get(business_type, "tenderBulletin")
