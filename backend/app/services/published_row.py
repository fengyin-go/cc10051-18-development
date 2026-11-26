"""发布数据（实际发布行）通用资源适配器。

让受控分发所用的发布行也能通过统一资源接口
``GET /api/published_row``、``GET /api/golden_record`` 等读取，
并支持统一动作入口的「调整数据归属」。真正的资格/清单逻辑仍在
``controlled_distribution`` 领域服务中。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services.controlled_distribution import controlled


class PublishedRowService(BaseModuleService):
    MODULE = "published_row"
    ENTITY = "发布数据行"
    LIST_FIELDS = ["记录编号", "客户名称", "实体名称", "版本标识", "发布批次", "归属地区", "归属依据"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["已发布"]
    ACTION_RULES = {"调整数据归属": "已发布"}
    NEGATIVE_ACTIONS: list[str] = []

    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        filters = filters or {}
        region = filters.get("归属地区") or filters.get("region")
        version = filters.get("版本标识") or filters.get("version")
        entity = filters.get("实体") or filters.get("实体名称")
        result = controlled.query_published_rows(
            entity=entity, version=version, region=region,
            keyword=keyword, page=page, size=size)
        return result["items"], int(result["total"])

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        for row in controlled.published_rows:
            if int(row["id"]) == int(entry_id):
                return row
        return None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        if action in {"调整数据归属", "调整归属", "变更归属地区"}:
            result = controlled.adjust_attribution(entry_id, {})
            if result.get("ok"):
                return result["row"], str(result.get("message"))
            return None, str(result.get("message"))
        return None, f"动作「{action}」不属于{self.MODULE}可执行范围"


class GoldenRecordAdapter(PublishedRowService):
    MODULE = "golden_record"


class PublishDataAdapter(PublishedRowService):
    MODULE = "publish_data"
