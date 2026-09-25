"""光伏电站接口：维护电站档案，覆盖办理并网、申请限电、停运电站等动作。"""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.station import LIST_FIELDS, STATUS_ORDER, StationService

router = APIRouter(prefix="/api/station", tags=["光伏电站"])

service = StationService()


def _prepare_filters(
    code: str | None,
    region: str | None,
    status: str | None,
    keyword: str | None,
) -> tuple[str | None, str | None, str | None]:
    """归一化并校验列表与导出共用的筛选条件；条件不合法时说明原因。"""
    # keyword 是旧版“按电站编码检索”的参数名，保留兼容，与 code 二选一
    code = (code or keyword or "").strip() or None
    region = (region or "").strip() or None
    status = (status or "").strip() or None
    if status is not None and status not in STATUS_ORDER:
        allowed = "、".join(STATUS_ORDER)
        raise HTTPException(status_code=400, detail=f"电站状态仅支持：{allowed}；收到的是「{status}」")
    return code, region, status


@router.get("", response_model=PageResult[dict])
def list_entries(
    code: str | None = Query(default=None, description="按电站编码检索"),
    region: str | None = Query(default=None, description="按所属区域检索"),
    status: str | None = Query(default=None, description="在建、已投运、限电中、已停运"),
    keyword: str | None = Query(default=None, description="电站编码检索的旧参数名，与 code 等价"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按电站编码、所属区域与状态过滤光伏电站列表；筛选、分页、导出共用同一套条件。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1 or size > 200:
        raise HTTPException(status_code=400, detail="每页条数需在 1 到 200 之间，请调整分页范围")
    code, region, status = _prepare_filters(code, region, status, keyword)
    items, total = service.list_entries(
        code=code, region=region, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    code: str | None = Query(default=None, description="按电站编码检索"),
    region: str | None = Query(default=None, description="按所属区域检索"),
    status: str | None = Query(default=None, description="在建、已投运、限电中、已停运"),
    keyword: str | None = Query(default=None, description="电站编码检索的旧参数名，与 code 等价"),
) -> StreamingResponse:
    """导出当前筛选条件下的全部命中电站：列、顺序与列表完全一致，无命中时给空表头并说明，不返回错位数据。"""
    code, region, status = _prepare_filters(code, region, status, keyword)
    items = service.export_entries(code=code, region=region, status=status)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(LIST_FIELDS)
    for item in items:
        writer.writerow([item.get(field) if item.get(field) is not None else "" for field in LIST_FIELDS])
    # UTF-8 BOM 让 Excel 直接打开不乱码
    content = "\ufeff" + buffer.getvalue()

    filename = quote("光伏电站清单.csv")
    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=station.csv; filename*=UTF-8''{filename}"},
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
