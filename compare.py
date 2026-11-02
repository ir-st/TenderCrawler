"""爬取结果对比：与同一站点上一次快照比较新增/消失记录。"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SNAPSHOT_RE = re.compile(
    r"^(?:web|tenders)_(?P<site>[^_]+)_(?P<stamp>\d{8}_\d{6})\.json$"
)


def record_key(row: dict) -> str:
    """与爬虫去重逻辑一致：business_id + business_type。"""
    bid = str(row.get("business_id") or "").strip()
    bt = str(row.get("business_type") or "").strip()
    if bid:
        return f"{bid}|{bt}"
    url = str(row.get("portal_url") or "").strip()
    if url:
        return f"{url}|{bt}"
    title = str(row.get("title") or "").strip()
    return f"{title}|{bt}"


def load_records(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"JSON 根节点应为数组: {path}")
        return data
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows: list[dict] = []
            for row in csv.DictReader(f):
                cats = (row.get("categories") or "").strip()
                row["categories"] = [c for c in cats.split("|") if c] if cats else []
                rows.append(row)
            return rows
    raise ValueError(f"不支持的文件格式: {path}")


def find_previous_snapshot(
    output_dir: Path,
    site_id: str,
    current_json: Path,
) -> Path | None:
    snapshots: list[tuple[str, Path]] = []
    for p in output_dir.glob("*.json"):
        if p.name.startswith("compare_"):
            continue
        m = SNAPSHOT_RE.match(p.name)
        if not m or m.group("site") != site_id:
            continue
        snapshots.append((m.group("stamp"), p))
    snapshots.sort(key=lambda x: x[0], reverse=True)
    current_resolved = current_json.resolve()
    for i, (_, path) in enumerate(snapshots):
        if path.resolve() == current_resolved:
            if i + 1 < len(snapshots):
                return snapshots[i + 1][1]
            return None
    return None


@dataclass
class CompareResult:
    site_id: str
    current_path: str
    previous_path: str | None
    current_total: int
    previous_total: int
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    unchanged_count: int = 0

    @property
    def has_previous(self) -> bool:
        return self.previous_path is not None

    def summary(self) -> dict:
        return {
            "site_id": self.site_id,
            "current_path": self.current_path,
            "previous_path": self.previous_path,
            "current_total": self.current_total,
            "previous_total": self.previous_total,
            "added_count": len(self.added),
            "removed_count": len(self.removed),
            "unchanged_count": self.unchanged_count,
            "has_previous": self.has_previous,
        }

    def to_dict(self) -> dict:
        data = self.summary()
        data["added"] = self.added
        data["removed"] = self.removed
        return data


def compare_record_lists(
    current: list[dict],
    previous: list[dict],
    *,
    site_id: str = "",
    current_path: str = "",
    previous_path: str | None = None,
) -> CompareResult:
    prev_map = {record_key(r): r for r in previous}
    curr_map = {record_key(r): r for r in current}

    added = [curr_map[k] for k in curr_map if k not in prev_map]
    removed = [prev_map[k] for k in prev_map if k not in curr_map]
    unchanged = sum(1 for k in curr_map if k in prev_map)

    return CompareResult(
        site_id=site_id,
        current_path=current_path,
        previous_path=previous_path,
        current_total=len(current),
        previous_total=len(previous),
        added=added,
        removed=removed,
        unchanged_count=unchanged,
    )


def compare_with_previous(
    output_dir: Path,
    *,
    site_id: str,
    current_records: list[dict] | None = None,
    current_json_path: Path,
) -> CompareResult:
    previous_path = find_previous_snapshot(output_dir, site_id, current_json_path)
    current_path = str(current_json_path)
    if current_records is None:
        current_records = load_records(current_json_path)

    if previous_path is None:
        return CompareResult(
            site_id=site_id,
            current_path=current_path,
            previous_path=None,
            current_total=len(current_records),
            previous_total=0,
        )

    previous_records = load_records(previous_path)
    return compare_record_lists(
        current_records,
        previous_records,
        site_id=site_id,
        current_path=current_path,
        previous_path=str(previous_path),
    )


def save_compare_json(result: CompareResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def format_compare_report(result: CompareResult) -> str:
    if not result.has_previous:
        return f"共 {result.current_total} 条，无同站点历史快照可对比。"
    lines = [
        f"对比：{Path(result.previous_path).name} → {Path(result.current_path).name}",
        f"上次 {result.previous_total} 条 → 本次 {result.current_total} 条",
        f"新增 {len(result.added)} 条，消失 {len(result.removed)} 条，未变 {result.unchanged_count} 条",
    ]
    if result.added:
        lines.append("\n【新增】")
        for r in result.added[:20]:
            lines.append(f"  + {r.get('title', '')}")
        if len(result.added) > 20:
            lines.append(f"  … 另有 {len(result.added) - 20} 条")
    if result.removed:
        lines.append("\n【消失】")
        for r in result.removed[:20]:
            lines.append(f"  - {r.get('title', '')}")
        if len(result.removed) > 20:
            lines.append(f"  … 另有 {len(result.removed) - 20} 条")
    return "\n".join(lines)
