"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    # 允许领用/授权类动作携带 region、preview_id、version 等扩展参数。
    model_config = ConfigDict(extra="allow")

    action: str
    remark: str | None = None
    region: str | None = None
    地区: str | None = None
    preview_id: str | None = None
    version: str | None = None
    batch_id: int | str | None = None
    confirmation_code: str | None = None
    basis: str | None = None
    source: str | None = None
