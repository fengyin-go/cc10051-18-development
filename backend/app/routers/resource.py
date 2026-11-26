"""统一资源接口：查询、导出、登记和动作按模块 key 分派到领域服务。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services import service_for

router = APIRouter(prefix="/api", tags=["业务资源"])


def require_service(module: str):
    service = service_for(module)
    if service is None:
        raise HTTPException(status_code=404, detail=f"未知业务模块：{module}")
    return service


@router.get("/{module}", response_model=PageResult[dict])
def list_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, total = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{module}/export")
def export_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, _ = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=1, size=1_000_000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *service.LIST_FIELDS, "status"])
    for item in items:
        values = [item.get("id"), *(item.get(field, "") for field in service.LIST_FIELDS),
                  item.get("status", "")]
        writer.writerow([
            "'" + str(value) if str(value or "").startswith(("=", "+", "-", "@")) else value
            for value in values
        ])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module}.csv"'},
    )


@router.get("/{module}/{entry_id}", response_model=dict)
def get_entry(module: str, entry_id: int) -> dict[str, Any]:
    service = require_service(module)
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{service.ENTITY} {entry_id} 不存在或已归档")
    return entry


@router.post("/{module}", response_model=ActionResult)
def create_entry(module: str, payload: EntryPayload) -> ActionResult:
    service = require_service(module)
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"{service.ENTITY}已登记", entry=entry)


@router.post("/{module}/{entry_id}/actions", response_model=ActionResult)
def run_action(module: str, entry_id: int, payload: ActionPayload) -> ActionResult:
    action = payload.action.strip()
    # 受控分发/按授权地区领用相关的中文动作，统一委派给受控分发领域服务，
    # 让既有通用动作入口也能承载新业务。
    special = _maybe_controlled_action(module, entry_id, action, payload)
    if special is not None:
        return special
    service = require_service(module)
    entry, message = service.run_action(entry_id, action)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


def _maybe_controlled_action(
    module: str, entry_id: int, action: str, payload: ActionPayload
) -> ActionResult | None:
    from app.services.controlled_distribution import controlled

    extra = payload.model_dump(exclude_none=True)
    extra.update(payload.model_extra or {})
    region = payload.region or payload.地区 or extra.get("地区范围") or "北区"

    # 管理员调整发布行的数据归属。
    if module in {"published_row", "publish_row", "cd_published_row"} and action in {
        "调整数据归属", "调整归属", "变更归属地区", "修改归属地区",
    }:
        result = controlled.adjust_attribution(entry_id, extra)
        return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                            entry=result)

    if module == "golden_publish" and action in {"领用历史", "查看领用历史", "分发领用历史"}:
        result = controlled.history(batch_id=entry_id)
        return ActionResult(ok=True, message="该版本的领用历史已生成", entry=result)

    if module != "subscriber_mgr":
        return None

    if action in {"生成预览", "预览", "预览领用", "领用预览", "按地区领用预览", "查询受控清单"}:
        body = {"subscriber_id": entry_id, "region": region, **extra}
        result = controlled.make_preview(body)
        return ActionResult(ok=True, message="受控分发清单预览已生成", entry=result)

    if action in {"确认领取", "确认领用", "领取", "领用", "按地区领用", "发起领用", "申请领用"}:
        body = {"subscriber_id": entry_id, "region": region, **extra}
        result = controlled.create_claim(body)
        return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                            entry=result)

    if action in {"继续领取", "继续下载", "断点续领", "恢复交付"}:
        code = payload.confirmation_code or extra.get("code") or ""
        result = controlled.continue_confirmation(str(code))
        return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                            entry=result)

    if action in {"撤销授权", "撤去地区权限", "撤销地区授权", "收回权限", "停用地区授权"}:
        result = controlled.change_grant(
            {"subscriber_id": entry_id, "region": region, "action": "revoke", **extra})
        return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                            entry=result)

    if action in {"授予地区", "授予授权", "新增授权", "授予地区授权"}:
        result = controlled.change_grant(
            {"subscriber_id": entry_id, "region": region, "action": "grant", **extra})
        return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                            entry=result)

    if action in {"领用历史", "我的领用", "交付历史"}:
        result = {"items": controlled.list_confirmations(subscriber=entry_id)}
        return ActionResult(ok=True, message="该订阅方的领用记录", entry=result)

    return None
