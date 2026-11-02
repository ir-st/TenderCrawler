"""TenderCrawler 版本信息。

版本号遵循语义化版本（MAJOR.MINOR.PATCH）：
- MAJOR：不兼容的重构或功能移除
- MINOR：新功能（向下兼容）
- PATCH：缺陷修复与体验改进
"""

__version__ = "1.0.0"

# 当前版本的发布日期（YYYY-MM-DD）
VERSION_DATE = "2026-11-02"

# 版本说明（简要列出本次变更，供 --version 与文档引用）
VERSION_NOTES = (
    "首个声明版本：修复 cebpub 全站 https 迁移导致的抓取失败；"
    "适配平台 VAPTCHA 验证（每组合独立会话 + 翻页受限优雅降级）；"
    "修复 CLI --types 在 ccgp 站点下的参数限制。"
)
