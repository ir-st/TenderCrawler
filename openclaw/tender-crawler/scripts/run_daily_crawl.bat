@echo off
chcp 65001 >nul
setlocal

if not defined TENDER_CRAWLER_HOME (
  set "TENDER_CRAWLER_HOME=%~dp0..\..\.."
)
set "TENDER_CRAWLER_HOME=%TENDER_CRAWLER_HOME:"=%"

where py >nul 2>&1 && set "PY=py -3" || set "PY=python"

echo TenderCrawler 定时抓取
echo 项目目录: %TENDER_CRAWLER_HOME%
cd /d "%TENDER_CRAWLER_HOME%"

if not defined TENDER_CRAWLER_MAX_PAGES set "TENDER_CRAWLER_MAX_PAGES=3"

%PY% "%~dp0run_daily_crawl.py"
exit /b %ERRORLEVEL%
