"""光伏电站接口：维护电站档案，覆盖办理并网、申请限电、停运电站等动作。"""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.station import StationService

router = APIRouter(prefix="/api/station", tags=["光伏电站"])

service = StationService()

LIST_FIELDS = ["电站编码", "电站名称", "装机容量", "并网电压等级", "所属区域", "投运日期", "运维班组", "电站状态"]
STATUSES = ["在建", "已投运", "限电中", "已停运"]


def _normalize(value: str | None) -> str | None:
    """查询条件按空白归一：空串、纯空格视为没有填写，避免筛出一张空表。"""
    if value is None:
        return None
    text = value.strip()
    return text or None


def _query_filters(
    keyword: str | None,
    status: str | None,
    region: str | None,
) -> dict[str, str]:
    """列表、分页与导出共用的一套条件，口径在同一个地方收口。"""
    status_text = _normalize(status)
    if status_text is not None and status_text not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"电站状态「{status_text}」不在允许范围，可选：{'、'.join(STATUSES)}",
        )
    return {
        "keyword": _normalize(keyword) or "",
        "status": status_text or "",
        "region": _normalize(region) or "",
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按电站编码检索"),
    status: str | None = Query(default=None, description="在建、已投运、限电中、已停运"),
    region: str | None = Query(default=None, description="按所属区域检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按电站编码、所属区域与状态过滤光伏电站列表；条件不合法时说明原因。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码需从第 1 页开始，请检查翻页参数")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    filters = _query_filters(keyword, status, region)
    items, total = service.list_entries(
        keyword=filters["keyword"] or None,
        status=filters["status"] or None,
        region=filters["region"] or None,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按电站编码检索"),
    status: str | None = Query(default=None, description="在建、已投运、限电中、已停运"),
    region: str | None = Query(default=None, description="按所属区域检索"),
) -> StreamingResponse:
    """导出当前过滤条件下的全量电站；条件命中为空时说明原因，不给空文件。"""
    filters = _query_filters(keyword, status, region)
    items, total = service.list_entries(
        keyword=filters["keyword"] or None,
        status=filters["status"] or None,
        region=filters["region"] or None,
        page=1,
        size=10000,
    )
    if total == 0:
        reasons = []
        if filters["keyword"]:
            reasons.append(f"电站编码包含「{filters['keyword']}」")
        if filters["region"]:
            reasons.append(f"所属区域包含「{filters['region']}」")
        if filters["status"]:
            reasons.append(f"电站状态为「{filters['status']}」")
        cause = "、".join(reasons) if reasons else "系统中尚未登记电站档案"
        raise HTTPException(status_code=404, detail=f"当前条件（{cause}）没有命中任何电站，未生成导出文件")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(LIST_FIELDS)
    for row in items:
        values = []
        for field in LIST_FIELDS:
            # 电站状态列与列表保持一致，取状态流转写入的 status，避免列内容错位
            value = row.get("status") if field == "电站状态" else row.get(field, "")
            values.append("" if value is None else value)
        writer.writerow(values)

    # utf-8-sig 会写入 BOM，Excel 直接打开中文表头不乱码
    payload = buffer.getvalue().encode("utf-8-sig")
    filename = quote("光伏电站清单.csv")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条电站档案明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"电站档案 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条电站档案，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="电站档案已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条电站档案执行办理并网、申请限电、停运电站；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
