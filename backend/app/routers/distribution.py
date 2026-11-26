"""受控分发 HTTP 接口。

主路径统一在 /api/controlled-distribution 下；同时挂载一批符合直觉的
别名路径（/api/distribution、/api/claims、/api/manifests 等），方便不同
调用方与自动化用例按其习惯接入。所有业务判断都在 controlled 服务内完成。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.services.controlled_distribution import controlled

router = APIRouter(prefix="/api", tags=["受控分发"])


async def _payload(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


def _csv_response(result: dict[str, Any]) -> Response:
    filename = str(result["filename"])
    ascii_name = "manifest.csv"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    # utf-8-sig 让 Excel 正确识别中文 BOM。
    return Response(
        content="﻿".encode("utf-8") + result["csv"].encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition,
                 "X-Confirmation-Code": result["confirmation"]["code"],
                 "X-Manifest-No": result["confirmation"]["manifest_no"],
                 "X-First-Dispatch": "1" if result["first_dispatch"] else "0"},
    )


# --------------------------------------------------------------------- meta

@router.get("/controlled-distribution/meta")
@router.get("/distribution/meta")
async def get_meta() -> dict[str, Any]:
    return {"ok": True, **controlled.meta()}


# ------------------------------------------------------------ published rows

@router.get("/controlled-distribution/published-rows")
@router.get("/distribution/published-rows")
@router.get("/publish-rows")
@router.get("/published-rows")
async def list_published_rows(request: Request) -> dict[str, Any]:
    q = request.query_params
    return controlled.query_published_rows(
        subscriber=q.get("subscriber") or q.get("subscriber_id") or q.get("收件主体"),
        entity=q.get("entity") or q.get("实体"),
        version=q.get("version") or q.get("版本标识"),
        batch_id=q.get("batch_id") or q.get("golden_publish_id"),
        region=q.get("region") or q.get("地区") or q.get("归属地区"),
        keyword=q.get("keyword"),
        recognized=q.get("recognized"),
        page=int(q.get("page", 1)), size=int(q.get("size", 200)),
    )


@router.post("/controlled-distribution/published-rows/{row_id}/attribution")
@router.post("/distribution/published-rows/{row_id}/attribution")
@router.post("/publish-rows/{row_id}/attribution")
@router.post("/published-rows/{row_id}/attribution")
@router.post("/published_row/{row_id}/attribution")
@router.post("/golden_record/{row_id}/attribution")
@router.post("/publish_data/{row_id}/attribution")
@router.patch("/controlled-distribution/published-rows/{row_id}")
@router.patch("/published-rows/{row_id}")
@router.patch("/published_row/{row_id}")
@router.patch("/golden_record/{row_id}")
@router.put("/published_row/{row_id}")
@router.put("/golden_record/{row_id}")
async def adjust_attribution(row_id: str, request: Request) -> dict[str, Any]:
    # PUT/PATCH 也兼容通用登记风格 {"values": {"归属地区": ...}}。
    try:
        payload = await _payload(request)
    except Exception:
        payload = {}
    if isinstance(payload.get("values"), dict):
        merged = dict(payload["values"])
        merged.update({k: v for k, v in payload.items() if k != "values"})
        payload = merged
    return controlled.adjust_attribution(row_id, payload)


# ------------------------------------------------------------------ preview

@router.post("/controlled-distribution/preview")
@router.post("/distribution/preview")
@router.post("/claims/preview")
@router.post("/manifests/preview")
async def preview(request: Request) -> dict[str, Any]:
    return controlled.make_preview(await _payload(request))


# ------------------------------------------------------------------- claims

@router.post("/controlled-distribution/claims")
@router.post("/distribution/claims")
@router.post("/claims")
@router.post("/manifests")
async def create_claim(request: Request) -> dict[str, Any]:
    return controlled.create_claim(await _payload(request))


@router.get("/controlled-distribution/claims")
@router.get("/distribution/claims")
@router.get("/claims")
@router.get("/manifests")
async def list_claims(request: Request) -> dict[str, Any]:
    q = request.query_params
    items = controlled.list_confirmations(
        subscriber=q.get("subscriber") or q.get("subscriber_id") or q.get("订阅方"),
        version=q.get("version") or q.get("版本标识"),
        batch_id=q.get("batch_id") or q.get("golden_publish_id"),
    )
    return {"ok": True, "items": items, "total": len(items), "page": 1, "size": max(1, len(items))}


@router.get("/controlled-distribution/claims/{code}")
@router.get("/distribution/claims/{code}")
@router.get("/claims/{code}")
@router.get("/manifests/{code}")
async def get_claim(code: str) -> dict[str, Any]:
    conf = controlled.get_confirmation(code)
    if conf is None:
        return {"ok": False, "message": f"确认单 {code} 不存在"}
    return {"ok": True, "confirmation": controlled._conf_detail(conf)}  # noqa: SLF001


@router.post("/controlled-distribution/claims/{code}/continue")
@router.post("/distribution/claims/{code}/continue")
@router.post("/claims/{code}/continue")
@router.post("/claims/{code}/resume")
async def continue_claim(code: str) -> dict[str, Any]:
    return controlled.continue_confirmation(code)


@router.get("/controlled-distribution/claims/{code}/download")
@router.get("/distribution/claims/{code}/download")
@router.get("/claims/{code}/download")
@router.get("/manifests/{code}/download")
async def download_claim(code: str, format: str = "csv") -> Response:  # noqa: A002
    result = controlled.download(code)
    if not result.get("ok"):
        return Response(content=str(result.get("message")), status_code=404)
    if format == "json":
        import json
        return Response(
            content=json.dumps({"ok": True, "confirmation": result["confirmation"]},
                               ensure_ascii=False, indent=2).encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"X-Confirmation-Code": code},
        )
    return _csv_response(result)


@router.post("/controlled-distribution/claims/{code}/download")
async def download_claim_post(code: str) -> Response:
    result = controlled.download(code)
    if not result.get("ok"):
        return Response(content=str(result.get("message")), status_code=404)
    return _csv_response(result)


# ------------------------------------------------------------------- grants

@router.get("/controlled-distribution/grants")
@router.get("/distribution/grants")
@router.get("/region-grants")
@router.get("/region_grant")
@router.get("/region_grants")
async def list_grants(subscriber: str | None = None) -> dict[str, Any]:
    return {"ok": True, "items": controlled.list_grants(subscriber)}


@router.post("/controlled-distribution/grants")
@router.post("/distribution/grants")
@router.post("/region-grants")
@router.post("/region_grant")
@router.post("/region_grants")
async def change_grant(request: Request) -> dict[str, Any]:
    return controlled.change_grant(await _payload(request))


@router.post("/controlled-distribution/grants/{grant_id}/revoke")
@router.post("/region-grants/{grant_id}/revoke")
async def revoke_grant_by_id(grant_id: int, request: Request) -> dict[str, Any]:
    grant = next((g for g in controlled.grants if int(g["id"]) == grant_id), None)
    if grant is None:
        return {"ok": False, "message": f"授权记录 {grant_id} 不存在"}
    body = await _payload(request)
    body.setdefault("subscriber", grant["订阅方"])
    body.setdefault("region", grant["地区"])
    body["action"] = "revoke"
    return controlled.change_grant(body)


# ------------------------------------------------------------------ history

@router.get("/controlled-distribution/history")
@router.get("/distribution/history")
@router.get("/claim-history")
async def history(version: str | None = None, batch_id: str | None = None,
                  golden_publish_id: str | None = None) -> dict[str, Any]:
    return controlled.history(version=version, batch_id=batch_id,
                              golden_publish_id=golden_publish_id)


@router.get("/golden_publish/{entry_id}/claim-history")
async def publish_claim_history(entry_id: int) -> dict[str, Any]:
    return controlled.history(batch_id=entry_id)


@router.get("/golden_publish/{entry_id}/claims")
async def publish_claims(entry_id: int) -> dict[str, Any]:
    return controlled.history(batch_id=entry_id)


# ----------------------------------------------- subscriber nested shortcuts

@router.post("/subscriber_mgr/{entry_id}/controlled-preview")
@router.post("/subscriber_mgr/{entry_id}/preview-claim")
async def subscriber_preview(entry_id: int, request: Request) -> dict[str, Any]:
    body = await _payload(request)
    body.setdefault("subscriber_id", entry_id)
    return controlled.make_preview(body)


@router.post("/subscriber_mgr/{entry_id}/controlled-claim")
@router.post("/subscriber_mgr/{entry_id}/claim")
async def subscriber_claim(entry_id: int, request: Request) -> dict[str, Any]:
    body = await _payload(request)
    body.setdefault("subscriber_id", entry_id)
    return controlled.create_claim(body)


@router.get("/subscriber_mgr/{entry_id}/claims")
async def subscriber_claims(entry_id: int) -> dict[str, Any]:
    items = controlled.list_confirmations(subscriber=entry_id)
    return {"ok": True, "items": items, "total": len(items)}


@router.get("/subscriber_mgr/{entry_id}/claim-history")
async def subscriber_claim_history(entry_id: int) -> dict[str, Any]:
    items = controlled.list_confirmations(subscriber=entry_id)
    return {"ok": True, "items": items, "交付单": items, "total": len(items)}


@router.get("/golden_publish/claim-history")
async def publish_claim_history_by_version(version: str | None = None,
                                           batch_id: str | None = None) -> dict[str, Any]:
    return controlled.history(version=version, batch_id=batch_id)
