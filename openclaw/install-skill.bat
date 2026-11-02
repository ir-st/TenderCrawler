@echo off
chcp 65001 >nul
echo ========================================
echo   安装 TenderCrawler OpenClaw 技能
echo ========================================
echo.

set "SKILL_DIR=%~dp0tender-crawler"
set "DEFAULT_HOME=%~dp0.."
set "DEFAULT_HOME=%DEFAULT_HOME:~0,-1%"

if not defined TENDER_CRAWLER_HOME set "TENDER_CRAWLER_HOME=%DEFAULT_HOME%"

where openclaw >nul 2>&1
if errorlevel 1 (
    echo [提示] 未找到 openclaw CLI。请手动复制技能目录：
    echo   %SKILL_DIR%
    echo 到 workspace/skills/ 或 ~/.openclaw/skills/
    echo.
    echo 并在 openclaw.json 中配置 skills.entries.tender-crawler.env
    echo 参考: %SKILL_DIR%\openclaw.config.example.json5
    goto :cron_hint
)

echo 安装到全局技能目录 ^(--global^)...
openclaw skills install "%SKILL_DIR%" --global
if errorlevel 1 (
    echo [警告] 全局安装失败，尝试安装到当前 workspace...
    openclaw skills install "%SKILL_DIR%"
)

:cron_hint
echo.
echo 下一步：
echo   1. 编辑 openclaw.json，合并 %SKILL_DIR%\openclaw.config.example.json5
echo      将 TENDER_CRAWLER_HOME 改为: %TENDER_CRAWLER_HOME%
echo   2. 在 OpenClaw 中让 Agent 执行 cron.add，使用:
echo      %SKILL_DIR%\cron-job.example.json
echo   3. 手动测试: python "%TENDER_CRAWLER_HOME%\scheduled_crawl.py" --max-pages 1 --sites cebpub
echo.
pause
