"""光伏电站业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "station"
REQUIRED_FIELDS = ["电站编码", "电站名称", "装机容量"]
LIST_FIELDS = ["电站编码", "电站名称", "装机容量", "并网电压等级", "所属区域", "投运日期", "运维班组", "电站状态"]
STATUS_ORDER = ["在建", "已投运", "限电中", "已停运"]
ACTION_RULES = {"办理并网": "已投运", "申请限电": "限电中", "停运电站": "已停运"}
NEGATIVE_ACTIONS = []


class StationService:
    def list_entries(
        self,
        *,
        code: str | None = None,
        region: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(code=code, region=region, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._present(row) for row in page_rows], total

    def export_entries(
        self,
        *,
        code: str | None = None,
        region: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """导出与列表同一套筛选口径下的全量命中行，顺序与列表保持一致。"""
        rows = self._filter_rows(code=code, region=region, status=status)
        return [self._present(row) for row in rows]

    def _filter_rows(
        self,
        *,
        code: str | None,
        region: str | None,
        status: str | None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if code:
            rows = [row for row in rows if code in str(row.get("电站编码", ""))]
        if region:
            rows = [row for row in rows if region in str(row.get("所属区域", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def _present(self, row: dict[str, Any]) -> dict[str, Any]:
        """列表与导出共用的展示结构：只暴露列表列，电站状态以状态机里的值为准。"""
        item: dict[str, Any] = {"id": row.get("id")}
        for field in LIST_FIELDS:
            if field == "电站状态":
                item[field] = row.get("status")
            else:
                item[field] = row.get(field)
        return item

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"电站档案 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于光伏电站可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"电站档案已{action}"
