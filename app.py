#!/usr/bin/env python3
"""TenderCrawler Web 控制台。"""

from __future__ import annotations

import importlib
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, make_response, redirect, render_template, request, send_file

from bulletin_detail import enrich_tender_announcements
from compare import compare_with_previous, save_compare_json
from crawler import normalize_business_types, records_to_dicts, run_crawl, save_csv, save_json
from sites.registry import get_site
from detail import (
    CEBPUB_DETAIL_ACTION,
    CEBPUB_FRAME_DETAIL,
    business_keyword_for,
)
from version import __version__

app = Flask(__name__)
OUTPUT_DIR = Path("output")
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _site_payload(site) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "description": site.description,
        "portal_url": site.portal_url,
        "default_keywords": list(site.default_keywords),
        "suggested_keywords": list(site.suggested_keywords),
        "business_types": list(site.business_types),
        "default_delay": site.default_delay,
    }


@app.route("/")
def index():
    from sites import registry as sites_registry

    importlib.reload(sites_registry)
    all_kw: list[str] = []
    all_def: list[str] = []
    for s in sites_registry.list_sites():
        for k in s.suggested_keywords:
            if k not in all_kw:
                all_kw.append(k)
        for k in s.default_keywords:
            if k not in all_def:
                all_def.append(k)
    resp = make_response(
        render_template(
            "index.html",
            suggested_keywords=all_kw,
            default_keywords=all_def,
            version=__version__,
        )
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/sites")
def api_sites():
    # 每次请求重载配置，避免旧进程缓存导致关键词列表不更新
    from sites import registry as sites_registry

    importlib.reload(sites_registry)
    payload = {"sites": [_site_payload(s) for s in sites_registry.list_sites()]}
    resp = make_response(jsonify(payload))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/api/crawl")
def api_crawl():
    data = request.get_json(force=True) or {}
    site_id = (data.get("site_id") or "").strip()
    keywords = [k.strip() for k in (data.get("keywords") or []) if k.strip()]
    business_types = [
        t.strip() for t in (data.get("business_types") or []) if t.strip()
    ]

    if not site_id:
        return jsonify({"error": "请选择目标网站"}), 400
    if not keywords:
        return jsonify({"error": "请至少填写一个关键词"}), 400
    if not business_types:
        return jsonify({"error": "请至少选择一种业务类型"}), 400

    try:
        get_site(site_id)
        business_types = normalize_business_types(site_id, business_types)
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    job_id = uuid.uuid4().hex[:12]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = OUTPUT_DIR / f"web_{site_id}_{stamp}"

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "message": "任务已启动",
            "progress": [],
            "records": [],
            "stats": {},
            "error": None,
            "json_path": str(base.with_suffix(".json")),
            "csv_path": str(base.with_suffix(".csv")),
            "compare_path": str(OUTPUT_DIR / f"compare_{site_id}_{stamp}.json"),
            "compare": None,
            "bulletin_path": str(OUTPUT_DIR / f"bulletin_{site_id}_{stamp}.json"),
            "bulletin_status": "idle",
            "bulletin_message": "",
            "bulletin_progress": [],
            "bulletin_details": [],
            "created_at": stamp,
        }

    def worker():
        logs: list[str] = []

        def on_progress(**info):
            line = (
                f"{info.get('keyword')} / {info.get('business_type')} "
                f"第 {info.get('page')}/{info.get('total_pages')} 页"
            )
            with JOBS_LOCK:
                JOBS[job_id]["progress"].append(line)
                JOBS[job_id]["message"] = line

        def log(msg: str):
            logs.append(msg)
            with JOBS_LOCK:
                JOBS[job_id]["progress"].append(msg)
                JOBS[job_id]["message"] = msg

        try:
            records = run_crawl(
                site_id=site_id,
                keywords=keywords,
                business_types=business_types,
                strict_filter=bool(data.get("strict_filter", True)),
                date_start=(data.get("date_start") or "").strip(),
                date_stop=(data.get("date_stop") or "").strip(),
                max_pages=data.get("max_pages") or None,
                page_size=int(data.get("page_size") or 50),
                delay=float(data.get("delay") or 0),
                on_progress=on_progress,
                log=log,
            )
            json_path = Path(JOBS[job_id]["json_path"])
            save_json(records, json_path)
            save_csv(records, Path(JOBS[job_id]["csv_path"]))

            record_dicts = records_to_dicts(records)
            compare_result = compare_with_previous(
                OUTPUT_DIR,
                site_id=site_id,
                current_records=record_dicts,
                current_json_path=json_path,
            )
            compare_path = OUTPUT_DIR / f"compare_{site_id}_{stamp}.json"
            save_compare_json(compare_result, compare_path)

            by_cat: dict[str, int] = {}
            for r in records:
                for c in r.categories:
                    by_cat[c] = by_cat.get(c, 0) + 1

            with JOBS_LOCK:
                JOBS[job_id].update(
                    {
                        "status": "done",
                        "message": f"完成，共 {len(records)} 条",
                        "records": record_dicts,
                        "stats": {"total": len(records), "by_category": by_cat},
                        "compare": compare_result.summary(),
                        "compare_path": str(compare_path),
                        "error": None,
                    }
                )
            _start_bulletin_fetch(job_id, delay=max(float(data.get("delay") or 0), 0.6))
        except ValueError as exc:
            err = str(exc)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            if "Expecting value" in err or "JSONDecodeError" in err:
                err = (
                    "平台返回了无法解析的内容（多为限流或返回了网页）。"
                    "请确认已选择正确的目标网站与业务类型，增大请求间隔后重试。"
                    f" 原始信息: {exc}"
                )
            elif "Read timed out" in err or "ConnectionPool" in err:
                err = (
                    "连接采购网超时。该站响应较慢，请将请求间隔调至 4 秒以上，"
                    "减少关键词组合或限制抓取页数后重试。"
                    f" 原始信息: {exc}"
                )
        else:
            err = None
        if err is not None:
            with JOBS_LOCK:
                JOBS[job_id].update(
                    {
                        "status": "error",
                        "message": "抓取失败",
                        "error": err,
                    }
                )

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"job_id": job_id})


def _start_bulletin_fetch(job_id: str, *, delay: float = 0.6) -> bool:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("status") != "done":
            return False
        if job.get("bulletin_status") == "running":
            return False
        records = job.get("records") or []
        job["bulletin_status"] = "running"
        job["bulletin_message"] = "正在抓取招标公告详情…"
        job["bulletin_progress"] = []
        bulletin_path = job.get("bulletin_path")

    def bulletin_worker():
        def on_progress(current: int, total: int, row: dict):
            line = f"[{current}/{total}] {row.get('title', '')[:40]}"
            with JOBS_LOCK:
                JOBS[job_id]["bulletin_progress"].append(line)
                JOBS[job_id]["bulletin_message"] = (
                    f"招标详情 {current}/{total}"
                )

        try:
            details = enrich_tender_announcements(
                records,
                delay_seconds=delay,
                on_progress=on_progress,
            )
            if bulletin_path:
                Path(bulletin_path).write_text(
                    json.dumps(details, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            ok = sum(1 for d in details if d.get("status") == "ok")
            with JOBS_LOCK:
                JOBS[job_id].update(
                    {
                        "bulletin_status": "done",
                        "bulletin_message": (
                            f"完成，共 {len(details)} 条招标公告，"
                            f"成功解析 {ok} 条"
                        ),
                        "bulletin_details": details,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            with JOBS_LOCK:
                JOBS[job_id].update(
                    {
                        "bulletin_status": "error",
                        "bulletin_message": "招标详情抓取失败",
                        "bulletin_error": str(exc),
                    }
                )

    threading.Thread(target=bulletin_worker, daemon=True).start()
    return True


@app.post("/api/jobs/<job_id>/bulletin-details")
def api_fetch_bulletin_details(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    if job.get("status") != "done":
        return jsonify({"error": "请等待列表抓取完成"}), 400
    data = request.get_json(silent=True) or {}
    delay = float(data.get("delay") or 0.6)
    if not _start_bulletin_fetch(job_id, delay=delay):
        if job.get("bulletin_status") == "running":
            return jsonify({"ok": True, "message": "已在抓取中"})
        return jsonify({"error": "无法启动招标详情抓取"}), 400
    return jsonify({"ok": True})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404

    compare_detail = None
    compare_path = job.get("compare_path")
    if compare_path and Path(compare_path).is_file():
        try:
            cmp_data = json.loads(Path(compare_path).read_text(encoding="utf-8"))
            compare_detail = {
                "added": cmp_data.get("added") or [],
                "removed": cmp_data.get("removed") or [],
            }
        except (OSError, json.JSONDecodeError):
            compare_detail = None

    return jsonify(
        {
            "id": job["id"],
            "status": job["status"],
            "message": job["message"],
            "progress": job["progress"][-30:],
            "stats": job.get("stats") or {},
            "records": job.get("records") or [],
            "error": job.get("error"),
            "has_csv": Path(job["csv_path"]).is_file() if job.get("csv_path") else False,
            "has_json": Path(job["json_path"]).is_file() if job.get("json_path") else False,
            "compare": job.get("compare"),
            "compare_detail": compare_detail,
            "has_compare": Path(compare_path).is_file() if compare_path else False,
            "bulletin_status": job.get("bulletin_status"),
            "bulletin_message": job.get("bulletin_message"),
            "bulletin_progress": (job.get("bulletin_progress") or [])[-20:],
            "bulletin_details": job.get("bulletin_details") or [],
            "bulletin_error": job.get("bulletin_error"),
            "has_bulletin": Path(job["bulletin_path"]).is_file()
            if job.get("bulletin_path")
            else False,
        }
    )


@app.get("/detail/open")
def detail_open():
    """中转页：按官网方式加密并 POST 打开公示详情。"""
    job_id = (request.args.get("job_id") or "").strip()
    index = request.args.get("index", type=int)
    if not job_id or index is None:
        return "缺少参数 job_id 或 index", 400
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return "任务不存在或已过期，请重新抓取后再打开详情", 404
    records = job.get("records") or []
    if index < 0 or index >= len(records):
        return "记录不存在", 404
    rec = dict(records[index])
    if not rec.get("business_keyword"):
        rec["business_keyword"] = business_keyword_for(
            rec.get("business_type") or ""
        )
    rec.setdefault("list_type", "0")
    rec.setdefault("row_guid", "")
    detail_url = (rec.get("portal_url") or "").strip()
    if rec.get("list_type") == "direct" and detail_url.startswith("http"):
        return redirect(detail_url)
    if rec.get("source_site") == "ccgp" and detail_url.startswith("http"):
        return redirect(detail_url)
    return render_template(
        "detail_open.html",
        rec=rec,
        detail_action=CEBPUB_DETAIL_ACTION,
        frame_detail_base=CEBPUB_FRAME_DETAIL,
    )


@app.get("/api/download/<job_id>/<fmt>")
def api_download(job_id: str, fmt: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    if fmt == "csv":
        path = Path(job["csv_path"])
        mimetype = "text/csv"
    elif fmt == "json":
        path = Path(job["json_path"])
        mimetype = "application/json"
    elif fmt == "compare":
        path = Path(job["compare_path"])
        mimetype = "application/json"
    elif fmt == "bulletin":
        path = Path(job["bulletin_path"])
        mimetype = "application/json"
    else:
        return jsonify({"error": "格式无效"}), 400
    if not path.is_file():
        return jsonify({"error": "文件尚未生成"}), 404
    return send_file(path, as_attachment=True, mimetype=mimetype)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"TenderCrawler Web v{__version__}: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
