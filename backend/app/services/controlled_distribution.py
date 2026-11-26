"""按授权地区领用金记录的受控分发领域。

核心规则（与需求逐条对应）：

1. 领用请求必须带「发布批次/版本」和「地区范围」，服务端判断订阅资格，
   返回可以交付的「受控分发清单」。
2. 清单按「收件主体（订阅方）+ 实体 + 地区」生成，每一行都带归属依据，
   以及本次领取所用的授权来源，做事后核对。
3. 只有订阅了对应实体、且持有该行归属地区有效授权的收件方，才能领取该行。
4. 归属地区无法识别的行，一律拒绝，绝不能当成共享行放行。
5. 一笔交付（确认单）冻结唯一一版发布和唯一一份清单；之后断点续领、
   重复下载都只返回同一份冻结行，不混入授权变化后的新数据，也不新增派送。
6. 授权的授予/撤销全程留痕，撤销时点（revoked_at）可核对。
7. 发布端可按版本回查领用历史：交付单与被拒绝项都归属到同一订阅方。

本模块使用独立内存数据，不污染通用资源表与概览统计；服务重启后回到
「采购程序持有一份尚未领取的北区客户交付」的初始剧本。
"""
from __future__ import annotations

import csv
import io
import json
import threading
import uuid
from datetime import datetime
from typing import Any

from app.store import store

CUSTOMER_ENTITY = "客户"
CUSTOMER_ENTITY_CODE = "CUSTOMER"
CUSTOMER_VERSION = "v-customer-2026q3"
CUSTOMER_BATCH = "CUST-PUB-2026Q3"
CUSTOMER_BATCH_ID = 4
PROCUREMENT_SUBSCRIBER = "采购程序"
PROCUREMENT_SUBSCRIBER_ID = 4

REGIONS = ["北区", "南区", "东区", "西区"]
# 这些取值（以及空值）都视为「地区无法识别」。
UNKNOWN_REGION_TOKENS = {"", "无法识别", "未知", "待识别", "未识别", "unknown", "n/a", "na", "none", "null", "-", "—"}

# 拒绝原因码与面向页面/测试的固定中文措辞。
REASON = {
    "subscriber_inactive": "订阅方当前不是已生效状态，不能领用",
    "entity_not_subscribed": "未订阅实体「{entity}」，不能领取该实体记录",
    "region_unrecognized": "归属地区无法识别，不能当成共享行，已拒绝交付",
    "region_not_authorized": "没有「{region}」地区的有效授权，不能领取该行",
    "out_of_scope": "该行归属「{region}」，不在本次申请的「{scope}」地区范围内",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_unknown_region(region: Any) -> bool:
    return str(region if region is not None else "").strip().casefold() in UNKNOWN_REGION_TOKENS or \
        str(region if region is not None else "").strip() in {"地区无法识别"}


class ControlledDistributionService:
    """持有发布行、地区授权、确认单（交付单）与派送记录的内存领域服务。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.published_rows: list[dict[str, Any]] = []
        self.grants: list[dict[str, Any]] = []
        self.confirmations: list[dict[str, Any]] = []
        self.dispatches: list[dict[str, Any]] = []
        self.previews: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._seeded = False
        self.seed()

    # ------------------------------------------------------------------ ids

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def _new_code(self, prefix: str) -> str:
        return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    # ----------------------------------------------------------------- seed

    def seed(self) -> None:
        """播种剧本数据。重复调用安全（仅首次生效）。"""
        with self._lock:
            if self._seeded:
                return
            self._seeded = True
            self.published_rows = [
                {
                    "id": 1, "记录编号": "KH-2026-001", "客户名称": "北京北辰连锁超市有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "北区", "地区可识别": True,
                    "归属依据类型": "注册地址行政区划",
                    "归属依据": "注册地址「北京市朝阳区建国路88号」→ 行政区划北京市 → 北区",
                    "统一社会信用代码": "91110105MA01BEI001", "联系人": "王北辰", "联系电话": "010-88001001",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 2, "记录编号": "KH-2026-002", "客户名称": "天津津门港口服务有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "北区", "地区可识别": True,
                    "归属依据类型": "收货地址行政区划",
                    "归属依据": "默认收货地址「天津滨海新区塘沽港大道12号」→ 天津市 → 北区",
                    "统一社会信用代码": "91120116MA05BEI002", "联系人": "李津港", "联系电话": "022-66001002",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 3, "记录编号": "KH-2026-003", "客户名称": "石家庄冀北商贸有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "北区", "地区可识别": True,
                    "归属依据类型": "注册地址行政区划",
                    "归属依据": "注册地址「河北省石家庄市长安区中山东路1号」→ 华北片区冀北 → 北区",
                    "统一社会信用代码": "91130102MA07BEI003", "联系人": "张冀北", "联系电话": "0311-87001003",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 4, "记录编号": "KH-2026-004", "客户名称": "广州粤海智造股份有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "南区", "地区可识别": True,
                    "归属依据类型": "注册地址行政区划",
                    "归属依据": "注册地址「广东省广州市天河区珠江新城」→ 广东省 → 南区",
                    "统一社会信用代码": "91440101MA09NAN004", "联系人": "陈粤海", "联系电话": "020-38001004",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 5, "记录编号": "KH-2026-005", "客户名称": "深圳鹏湾电子科技有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "南区", "地区可识别": True,
                    "归属依据类型": "经营地址行政区划",
                    "归属依据": "实际经营地址「广东省深圳市南山区科技园南路」→ 广东省 → 南区",
                    "统一社会信用代码": "91440300MA05NAN005", "联系人": "林鹏湾", "联系电话": "0755-26001005",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 6, "记录编号": "KH-2026-006", "客户名称": "上海申沪商业集团有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "东区", "地区可识别": True,
                    "归属依据类型": "注册地址行政区划",
                    "归属依据": "注册地址「上海市黄浦区南京东路100号」→ 上海市 → 东区",
                    "统一社会信用代码": "91310101MA01DONG06", "联系人": "顾申沪", "联系电话": "021-63001006",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 7, "记录编号": "KH-2026-007", "客户名称": "成都锦里餐饮管理有限公司",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "西区", "地区可识别": True,
                    "归属依据类型": "注册地址行政区划",
                    "归属依据": "注册地址「四川省成都市武侯区锦里古街8号」→ 四川省 → 西区",
                    "统一社会信用代码": "91510107MA06XI0007", "联系人": "周锦里", "联系电话": "028-85001007",
                    "adjusted_at": None, "adjust_note": "",
                },
                {
                    "id": 8, "记录编号": "KH-2026-008", "客户名称": "渠道散客（地址与主体信息缺失）",
                    "实体编码": CUSTOMER_ENTITY_CODE, "实体名称": CUSTOMER_ENTITY,
                    "golden_publish_id": CUSTOMER_BATCH_ID,
                    "发布批次": CUSTOMER_BATCH, "版本标识": CUSTOMER_VERSION,
                    "归属地区": "无法识别", "地区可识别": False,
                    "归属依据类型": "依据缺失",
                    "归属依据": "缺少注册地址、收货地址与行政区划代码，无法识别归属地区；按受控分发规则不得作为共享行放行",
                    "统一社会信用代码": "", "联系人": "", "联系电话": "",
                    "adjusted_at": None, "adjust_note": "",
                },
            ]
            self.grants = [
                {
                    "id": 1, "subscriber_id": PROCUREMENT_SUBSCRIBER_ID,
                    "订阅方": PROCUREMENT_SUBSCRIBER, "地区": "北区",
                    "状态": "有效", "status": "有效",
                    "授权单号": "AUTH-PROC-BEI-202611",
                    "授权来源": "年度采购合同附件A·北区供应商数据授权条款",
                    "授权时间": "2026-11-18 09:30:00", "granted_at": "2026-11-18T09:30:00",
                    "撤销时间": None, "revoked_at": None, "撤销原因": "",
                },
                {
                    "id": 2, "subscriber_id": PROCUREMENT_SUBSCRIBER_ID,
                    "订阅方": PROCUREMENT_SUBSCRIBER, "地区": "西区",
                    "状态": "已撤销", "status": "已撤销",
                    "授权单号": "AUTH-PROC-XI-202610",
                    "授权来源": "上一期临时采购协作授权（已到期撤去）",
                    "授权时间": "2026-10-01 14:00:00", "granted_at": "2026-10-01T14:00:00",
                    "撤销时间": "2026-11-10 18:00:00", "revoked_at": "2026-11-10T18:00:00",
                    "撤销原因": "临时协作到期，撤去西区地区权限",
                },
            ]
            # 预安排一份「尚未领取的北区客户交付」：用同一套冻结逻辑生成，
            # 保证它引用唯一发布版本与唯一清单，且行内容是原始资格的快照。
            pre = self.evaluate(subscriber=PROCUREMENT_SUBSCRIBER, region="北区",
                                version=CUSTOMER_VERSION)
            self._freeze_confirmation(
                subscriber=self.resolve_subscriber(PROCUREMENT_SUBSCRIBER),  # type: ignore[arg-type]
                batch=self.resolve_batch(CUSTOMER_VERSION),
                region="北区",
                evaluation=pre,
                source="预安排",
                name="北区客户交付",
                code="CONF-PROC-BEI-0001",
                manifest_no="MAN-PROC-BEI-0001",
                created_at="2026-11-26 09:00:00",
            )

    # ------------------------------------------------------------- resolution

    def resolve_subscriber(self, ident: Any) -> dict[str, Any] | None:
        if ident is None:
            return None
        if isinstance(ident, dict):
            return ident
        text = str(ident).strip()
        rows = store.rows("subscriber_mgr")
        if text.isdigit():
            found = store.find("subscriber_mgr", int(text))
            if found:
                return found
        for row in rows:
            if str(row.get("订阅方标识", "")) == text or str(row.get("id", "")) == text:
                return row
        for row in rows:
            if text and text in str(row.get("订阅方标识", "")):
                return row
        # 受控数据里出现过的订阅方名称也允许（防止通用表被改动后失联）。
        if text == PROCUREMENT_SUBSCRIBER:
            return {"id": PROCUREMENT_SUBSCRIBER_ID, "订阅方标识": PROCUREMENT_SUBSCRIBER,
                    "订阅实体": CUSTOMER_ENTITY, "status": "已生效"}
        return None

    def resolve_batch(self, ident: Any = None, version: Any = None,
                      batch_id: Any = None) -> dict[str, Any] | None:
        rows = store.rows("golden_publish")
        if batch_id not in (None, ""):
            text = str(batch_id)
            if text.isdigit():
                found = store.find("golden_publish", int(text))
                if found:
                    return found
            for row in rows:
                if str(row.get("id")) == text:
                    return row
        target = str(version or ident or "").strip()
        if target:
            for row in rows:
                if str(row.get("版本标识", "")) == target or str(row.get("发布批次", "")) == target:
                    return row
            for row in rows:
                if target in str(row.get("版本标识", "")) or target in str(row.get("发布批次", "")):
                    return row
        found = store.find("golden_publish", CUSTOMER_BATCH_ID)
        return found or (rows[0] if rows else None)

    def _batch_version(self, batch: dict[str, Any] | None) -> str:
        return str((batch or {}).get("版本标识") or CUSTOMER_VERSION)

    def _batch_id(self, batch: dict[str, Any] | None) -> int | None:
        raw = (batch or {}).get("id")
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return CUSTOMER_BATCH_ID

    # ---------------------------------------------------------------- grants

    def grant_for_region(self, subscriber_name: str, region: str) -> dict[str, Any] | None:
        for g in self.grants:
            if g["订阅方"] == subscriber_name and g["地区"] == region and g.get("撤销时间") is None:
                return g
        return None

    def latest_grant_for_region(self, subscriber_name: str, region: str) -> dict[str, Any] | None:
        matches = [g for g in self.grants if g["订阅方"] == subscriber_name and g["地区"] == region]
        return matches[-1] if matches else None

    def list_grants(self, subscriber: Any = None) -> list[dict[str, Any]]:
        name = None
        if subscriber not in (None, ""):
            sub = self.resolve_subscriber(subscriber)
            name = str(sub.get("订阅方标识")) if sub else str(subscriber)
        with self._lock:
            rows = [dict(g) for g in self.grants if name is None or g["订阅方"] == name]
        rows.sort(key=lambda g: int(g["id"]))
        return rows

    def change_grant(self, payload: dict[str, Any]) -> dict[str, Any]:
        subscriber = payload.get("subscriber") or payload.get("subscriber_id") or payload.get("订阅方") or PROCUREMENT_SUBSCRIBER
        region = str(payload.get("region") or payload.get("地区") or "").strip()
        action = str(payload.get("action") or payload.get("动作") or payload.get("grant_action") or "").strip()
        sub = self.resolve_subscriber(subscriber)
        if sub is None:
            return {"ok": False, "message": f"订阅方不存在：{subscriber}"}
        if region not in REGIONS:
            return {"ok": False, "message": f"地区范围无效或缺失：{region or '（空）'}，可选 {'/'.join(REGIONS)}"}
        name = str(sub.get("订阅方标识"))
        do_revoke = action in {"revoke", "撤销", "撤销授权", "撤去权限", "收回权限", "停用"} or bool(payload.get("revoke"))
        with self._lock:
            if do_revoke:
                grant = self.grant_for_region(name, region)
                if grant is None:
                    latest = self.latest_grant_for_region(name, region)
                    if latest and latest.get("撤销时间"):
                        return {"ok": True, "message": f"{name} 的{region}授权此前已撤销", "grant": dict(latest)}
                    return {"ok": False, "message": f"{name} 没有有效的{region}授权可撤销"}
                ts = now_text()
                grant["状态"] = "已撤销"
                grant["status"] = "已撤销"
                grant["撤销时间"] = ts
                grant["revoked_at"] = now_iso()
                grant["撤销原因"] = str(payload.get("reason") or payload.get("原因") or "管理员撤去地区权限")
                return {"ok": True, "message": f"已撤销 {name} 的{region}授权，撤销时点 {ts}", "grant": dict(grant)}
            # 授予（幂等：已有有效授权直接返回）
            existing = self.grant_for_region(name, region)
            if existing:
                return {"ok": True, "message": f"{name} 已持有{region}有效授权", "grant": dict(existing)}
            grant = {
                "id": self._next(), "subscriber_id": sub.get("id"), "订阅方": name, "地区": region,
                "状态": "有效", "status": "有效",
                "授权单号": str(payload.get("授权单号") or self._new_code("AUTH")),
                "授权来源": str(payload.get("source") or payload.get("授权来源") or "管理员新增地区授权"),
                "授权时间": now_text(), "granted_at": now_iso(),
                "撤销时间": None, "revoked_at": None, "撤销原因": "",
            }
            self.grants.append(grant)
            return {"ok": True, "message": f"已授予 {name} {region}权限，授权时点 {grant['授权时间']}", "grant": dict(grant)}

    # ------------------------------------------------------------- attribution

    def adjust_attribution(self, row_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = next((r for r in self.published_rows if str(r["id"]) == str(row_id)
                        or str(r.get("记录编号")) == str(row_id)), None)
            if row is None:
                return {"ok": False, "message": f"发布行 {row_id} 不存在"}
            region = payload.get("region", payload.get("归属地区", None))
            basis = payload.get("basis", payload.get("归属依据", None))
            ts = now_text()
            history = row.setdefault("归属变更记录", [])
            history.append({
                "时间": ts,
                "原归属地区": row.get("归属地区"),
                "新归属地区": region if region is not None else row.get("归属地区"),
                "原归属依据": row.get("归属依据"),
                "新归属依据": basis if basis is not None else row.get("归属依据"),
                "操作人": payload.get("operator") or payload.get("操作人") or "管理员",
            })
            if region is not None and str(region).strip() != "":
                row["归属地区"] = str(region).strip()
            if basis is not None and str(basis).strip():
                row["归属依据"] = str(basis).strip()
            row["地区可识别"] = not is_unknown_region(row["归属地区"])
            if not row["地区可识别"]:
                row["归属地区"] = "无法识别"
                if "不能" not in str(row.get("归属依据", "")):
                    row["归属依据"] = str(row.get("归属依据", "")) + "；人工调整为无法识别地区，不得作为共享行"
            row["adjusted_at"] = ts
            row["adjust_note"] = str(payload.get("note") or payload.get("调整说明") or "管理员调整数据归属")
            return {"ok": True, "message": f"已调整 {row['记录编号']} 的数据归属为「{row['归属地区']}」", "row": dict(row)}

    # -------------------------------------------------------------- querying

    def query_published_rows(self, *, subscriber: Any = None, entity: str | None = None,
                             version: Any = None, batch_id: Any = None, region: str | None = None,
                             keyword: str | None = None, recognized: str | None = None,
                             page: int = 1, size: int = 200) -> dict[str, Any]:
        batch = self.resolve_batch(version=version, batch_id=batch_id) if (version or batch_id) else self.resolve_batch(None)
        ver = self._batch_version(batch)
        rows = [r for r in self.published_rows if r["版本标识"] == ver]
        if entity and str(entity).strip() and str(entity).strip() != CUSTOMER_ENTITY:
            rows = [r for r in rows if entity in {str(r.get("实体名称")), str(r.get("实体编码"))}]
        if region and str(region).strip() and str(region).strip() != "全部地区":
            rows = [r for r in rows if str(r.get("归属地区")) == str(region).strip()]
        if recognized in {"true", "false", True, False}:
            flag = recognized in {"true", True}
            rows = [r for r in rows if bool(r.get("地区可识别")) is flag]
        if keyword:
            kw = str(keyword).casefold()
            rows = [r for r in rows if kw in json.dumps(r, ensure_ascii=False).casefold()]
        total = len(rows)
        start = (max(1, page) - 1) * size
        paged = rows[start:start + size]

        sub = self.resolve_subscriber(subscriber) if subscriber not in (None, "") else None
        evals: dict[Any, dict[str, Any]] = {}
        if sub is not None:
            evaluation = self.evaluate(subscriber=sub, region=region, version=ver)
            for item in evaluation["all"]:
                evals[item["row_id"]] = item
        items = []
        for r in paged:
            item = dict(r)
            if r["id"] in evals:
                item["资格判定"] = {k: evals[r["id"]][k] for k in
                                   ("eligible", "reason", "reason_code", "权限来源", "grant_id")}
            items.append(item)
        return {"items": items, "total": total, "page": page, "size": size,
                "batch": self._batch_brief(batch), "subscriber": (str(sub.get("订阅方标识")) if sub else None)}

    def _batch_brief(self, batch: dict[str, Any] | None) -> dict[str, Any]:
        if not batch:
            return {}
        return {"id": batch.get("id"), "发布批次": batch.get("发布批次"),
                "版本标识": batch.get("版本标识"), "实体编码": batch.get("实体编码"),
                "status": batch.get("status")}

    # ------------------------------------------------------------ evaluation

    def _entity_subscribed(self, sub: dict[str, Any], entity: str) -> bool:
        blob = " ".join(str(sub.get(k, "")) for k in ("订阅实体", "订阅过滤", "收件主体")).replace("，", "、").replace(",", "、")
        if entity in blob:
            return True
        code = CUSTOMER_ENTITY_CODE if entity == CUSTOMER_ENTITY else entity
        return code.casefold() in blob.casefold()

    def evaluate(self, *, subscriber: Any, region: str | None = None,
                 version: Any = None, batch_id: Any = None,
                 at_time: datetime | None = None) -> dict[str, Any]:
        """按当前（或指定时点）授权与归属计算资格。返回 eligible/rejected/out_of_scope/all。"""
        sub = self.resolve_subscriber(subscriber)
        batch = self.resolve_batch(version=version, batch_id=batch_id)
        ver = self._batch_version(batch)
        sub_name = str(sub.get("订阅方标识")) if sub else str(subscriber)
        scope = str(region or "").strip()

        eligible: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        out_of_scope: list[dict[str, Any]] = []
        all_items: list[dict[str, Any]] = []

        sub_active = bool(sub) and sub.get("status") == "已生效"
        subscribed = bool(sub) and self._entity_subscribed(sub, CUSTOMER_ENTITY)

        for row in [r for r in self.published_rows if r["版本标识"] == ver]:
            row_region = str(row.get("归属地区") or "").strip()
            unknown = not row.get("地区可识别", not is_unknown_region(row_region)) or is_unknown_region(row_region)

            reason_code = ""
            reason = ""
            grant = None

            if not sub:
                reason_code, reason = "subscriber_not_found", f"订阅方不存在：{subscriber}"
            elif not sub_active:
                reason_code, reason = "subscriber_inactive", REASON["subscriber_inactive"]
            elif not subscribed:
                reason_code = "entity_not_subscribed"
                reason = REASON["entity_not_subscribed"].format(entity=CUSTOMER_ENTITY)
            elif unknown:
                reason_code, reason = "region_unrecognized", REASON["region_unrecognized"]
            else:
                # 地区可识别后，先看是否落在本次申请的地区范围内。
                if scope and scope != "全部地区" and row_region != scope:
                    reason_code = "out_of_scope"
                    reason = REASON["out_of_scope"].format(region=row_region, scope=scope)
                else:
                    grant = self.grant_for_region(sub_name, row_region)
                    if grant is None:
                        reason_code = "region_not_authorized"
                        reason = REASON["region_not_authorized"].format(region=row_region)
                        latest = self.latest_grant_for_region(sub_name, row_region)
                        if latest and latest.get("撤销时间"):
                            reason += f"；原授权已于 {latest['撤销时间']} 撤销"
                    else:
                        reason = ""

            item = {
                "row_id": row["id"],
                "记录编号": row.get("记录编号"),
                "客户名称": row.get("客户名称"),
                "实体": row.get("实体名称"),
                "版本标识": row.get("版本标识"),
                "发布批次": row.get("发布批次"),
                "region": row_region,
                "归属地区": "无法识别" if unknown else row_region,
                "地区可识别": not unknown,
                "归属依据": row.get("归属依据"),
                "归属依据类型": row.get("归属依据类型"),
                "eligible": reason_code == "",
                "reason_code": reason_code,
                "reason": reason,
                "grant_id": grant["id"] if grant else None,
                "授权单号": grant.get("授权单号") if grant else None,
                "权限来源": grant.get("授权来源") if grant else None,
                "授权时间": grant.get("授权时间") if grant else None,
                "撤销时间": grant.get("撤销时间") if grant else None,
                "subscriber": sub_name,
            }
            all_items.append(item)
            if item["eligible"]:
                eligible.append(item)
            elif reason_code == "out_of_scope":
                out_of_scope.append(item)
            else:
                rejected.append(item)

        return {
            "subscriber": sub_name,
            "subscriber_id": (sub or {}).get("id"),
            "subscriber_active": sub_active,
            "entity": CUSTOMER_ENTITY,
            "region": scope or "全部地区",
            "version": ver,
            "batch": self._batch_brief(batch),
            "eligible": eligible,
            "rejected": rejected,
            "out_of_scope": out_of_scope,
            "all": all_items,
            "counts": {
                "eligible": len(eligible), "rejected": len(rejected),
                "out_of_scope": len(out_of_scope), "total": len(all_items),
            },
            "evaluated_at": now_text(),
        }

    # --------------------------------------------------------------- preview

    def make_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        subscriber = payload.get("subscriber") or payload.get("subscriber_id") or payload.get("订阅方") or PROCUREMENT_SUBSCRIBER
        region = str(payload.get("region") or payload.get("地区范围") or payload.get("地区") or "北区").strip()
        version = payload.get("version") or payload.get("版本标识")
        batch_id = payload.get("batch_id") or payload.get("golden_publish_id") or payload.get("发布批次id")
        evaluation = self.evaluate(subscriber=subscriber, region=region, version=version, batch_id=batch_id)
        preview_id = self._new_code("PREV")
        snapshot = {
            "preview_id": preview_id,
            "created_at": now_text(),
            "subscriber": evaluation["subscriber"],
            "region": region,
            "version": evaluation["version"],
            "eligible_ids": [i["row_id"] for i in evaluation["eligible"]],
            "rejected_ids": [i["row_id"] for i in evaluation["rejected"]],
            "evaluation": evaluation,
        }
        with self._lock:
            self.previews[preview_id] = snapshot
        return {"ok": True, "preview_id": preview_id, "preview": snapshot, **evaluation}

    # ---------------------------------------------------------- confirmation

    def _line_from(self, eval_item: dict[str, Any]) -> dict[str, Any]:
        row = next(r for r in self.published_rows if r["id"] == eval_item["row_id"])
        return {
            "row_id": row["id"],
            "记录编号": row.get("记录编号"),
            "客户名称": row.get("客户名称"),
            "实体编码": row.get("实体编码"),
            "实体": row.get("实体名称"),
            "发布批次": row.get("发布批次"),
            "版本标识": row.get("版本标识"),
            "归属地区": eval_item["归属地区"],
            "归属依据": eval_item["归属依据"],
            "归属依据类型": eval_item.get("归属依据类型"),
            "grant_id": eval_item.get("grant_id"),
            "授权单号": eval_item.get("授权单号"),
            "权限来源": eval_item.get("权限来源"),
            "授权时间": eval_item.get("授权时间"),
            "统一社会信用代码": row.get("统一社会信用代码"),
            "联系人": row.get("联系人"),
            "联系电话": row.get("联系电话"),
        }

    def _freeze_confirmation(self, *, subscriber: dict[str, Any], batch: dict[str, Any] | None,
                             region: str, evaluation: dict[str, Any], source: str,
                             name: str | None = None, code: str | None = None,
                             manifest_no: str | None = None, created_at: str | None = None,
                             impact: dict[str, Any] | None = None,
                             preview_id: str | None = None) -> dict[str, Any]:
        ts = created_at or now_text()
        conf_code = code or self._new_code("CONF")
        man_no = manifest_no or self._new_code("MAN")
        lines = []
        for item in evaluation["eligible"]:
            line = self._line_from(item)
            line["清单编号"] = man_no
            lines.append(line)
        rejected = []
        for item in evaluation["rejected"]:
            rejected.append({
                "清单编号": man_no, "confirmation_code": conf_code,
                "subscriber": evaluation["subscriber"], "订阅方": evaluation["subscriber"],
                "row_id": item["row_id"], "记录编号": item["记录编号"], "客户名称": item["客户名称"],
                "实体": item["实体"], "版本标识": item["版本标识"],
                "归属地区": item["归属地区"], "reason_code": item["reason_code"],
                "拒绝原因": item["reason"], "归属依据": item["归属依据"],
                "handled_at": ts,
            })
        conf: dict[str, Any] = {
            "id": self._next(),
            "code": conf_code,
            "confirmation_code": conf_code,
            "manifest_no": man_no,
            "清单编号": man_no,
            "name": name or f"{region}客户受控交付",
            "交付单名称": name or f"{region}客户受控交付",
            "subscriber_id": subscriber.get("id"),
            "subscriber": evaluation["subscriber"],
            "订阅方": evaluation["subscriber"],
            "golden_publish_id": self._batch_id(batch),
            "batch": self._batch_brief(batch),
            "发布批次": evaluation.get("batch", {}).get("发布批次") if evaluation.get("batch") else CUSTOMER_BATCH,
            "version": evaluation["version"],
            "版本标识": evaluation["version"],
            "entity": CUSTOMER_ENTITY,
            "实体": CUSTOMER_ENTITY,
            "region": region,
            "地区范围": region,
            "source": source,
            "status": "待领取",
            "delivery_state": "未开始",
            "created_at": ts,
            "确认时间": ts,
            "first_downloaded_at": None,
            "last_downloaded_at": None,
            "首次领取时间": None,
            "dispatch_count": 0,
            "download_count": 0,
            "continue_count": 0,
            "preview_id": preview_id,
            "impact": impact,
            "lines": lines,
            "rejected": rejected,
        }
        self.confirmations.append(conf)
        return conf

    def create_claim(self, payload: dict[str, Any]) -> dict[str, Any]:
        subscriber = payload.get("subscriber") or payload.get("subscriber_id") or payload.get("订阅方") or PROCUREMENT_SUBSCRIBER
        region = str(payload.get("region") or payload.get("地区范围") or payload.get("地区") or "北区").strip()
        version = payload.get("version") or payload.get("版本标识")
        batch_id = payload.get("batch_id") or payload.get("golden_publish_id")
        preview_id = payload.get("preview_id") or payload.get("previewId")
        sub = self.resolve_subscriber(subscriber)
        if sub is None:
            return {"ok": False, "message": f"订阅方不存在：{subscriber}"}
        batch = self.resolve_batch(version=version, batch_id=batch_id)

        with self._lock:
            # 幂等：调用方带上同一 confirmation_code / code / idempotency_key 时返回原确认单。
            code_hint = payload.get("confirmation_code") or payload.get("code")
            idem = code_hint or payload.get("idempotency_key")
            if idem:
                existing = self.get_confirmation(idem)
                if existing:
                    return {"ok": True, "idempotent": True, "message": "同一确认已存在，继续使用原确认单",
                            "confirmation": self._conf_detail(existing), "impact": existing.get("impact")}

            evaluation = self.evaluate(subscriber=sub, region=region, version=version, batch_id=batch_id)

            impact = None
            preview = self.previews.get(str(preview_id)) if preview_id else None
            if preview:
                before = set(preview["eligible_ids"])
                now_ids = {i["row_id"] for i in evaluation["eligible"]}
                removed_ids = before - now_ids
                added_ids = now_ids - before
                id_map = {i["row_id"]: i for i in evaluation["all"]}
                impact = {
                    "preview_id": preview_id,
                    "preview_at": preview.get("created_at"),
                    "removed": [self._impact_brief(id_map[i]) for i in removed_ids if i in id_map],
                    "added": [self._impact_brief(id_map[i]) for i in added_ids if i in id_map],
                    "unchanged_count": len(before & now_ids),
                    "summary": self._impact_summary(removed_ids, added_ids, id_map, len(before & now_ids)),
                    "affected": bool(removed_ids or added_ids),
                }

            if not evaluation["subscriber_active"]:
                return {"ok": False,
                        "message": "订阅方未处于已生效状态，服务端判定无订阅资格；原有预览中的记录均会被拦下",
                        "evaluation": evaluation, "impact": impact, "counts": evaluation["counts"]}
            if not evaluation["all"] or (evaluation["all"] and
                                         all(i["reason_code"] == "entity_not_subscribed" for i in evaluation["all"])):
                return {"ok": False,
                        "message": f"订阅方未订阅实体「{CUSTOMER_ENTITY}」，服务端判定无领取资格",
                        "evaluation": evaluation, "impact": impact, "counts": evaluation["counts"]}

            conf = self._freeze_confirmation(
                subscriber=sub, batch=batch, region=region, evaluation=evaluation,
                source="自助领用", name=payload.get("name") or None,
                code=(str(code_hint) if code_hint else None),
                preview_id=str(preview_id) if preview_id else None, impact=impact)
            detail = self._conf_detail(conf)
            message = f"已生成受控分发清单 {conf['manifest_no']}，可交付 {len(conf['lines'])} 行，拒绝 {len(conf['rejected'])} 行"
            if impact and impact["affected"]:
                message += "；检测到预览后的授权/归属变化：" + impact["summary"]
            return {"ok": True, "message": message,
                    "confirmation": detail, "delivery": detail, "entry": detail,
                    "confirmation_code": conf["code"], "code": conf["code"],
                    "manifest_no": conf["manifest_no"],
                    "manifest": {"manifest_no": conf["manifest_no"], "清单编号": conf["manifest_no"],
                                 "confirmation_code": conf["code"], "version": conf["version"],
                                 "版本标识": conf["version"], "region": conf["region"],
                                 "lines": detail["lines"], "eligible": detail["lines"],
                                 "rejected": detail["rejected"]},
                    "impact": impact, "counts": evaluation["counts"]}

    def _impact_brief(self, item: dict[str, Any]) -> dict[str, Any]:
        return {"row_id": item["row_id"], "记录编号": item["记录编号"], "客户名称": item["客户名称"],
                "归属地区": item["归属地区"], "eligible_now": item["eligible"],
                "reason": item["reason"], "reason_code": item["reason_code"]}

    def _impact_summary(self, removed: set, added: set, id_map: dict, unchanged: int) -> str:
        parts = []
        if removed:
            names = "、".join(f"{id_map[i]['记录编号']} {id_map[i]['客户名称']}" for i in removed if i in id_map)
            parts.append(f"{len(removed)} 条在预览后失去领取资格（{names}）")
        if added:
            names = "、".join(f"{id_map[i]['记录编号']} {id_map[i]['客户名称']}" for i in added if i in id_map)
            parts.append(f"{len(added)} 条因新授权/归属调整新纳入清单（{names}）")
        if not parts:
            return f"授权未影响清单，{unchanged} 条记录与预览一致"
        return "；".join(parts) + f"；其余 {unchanged} 条不受影响"

    # --------------------------------------------------------- query confs

    def get_confirmation(self, code_or_id: Any) -> dict[str, Any] | None:
        text = str(code_or_id).strip()
        for conf in self.confirmations:
            if str(conf["code"]) == text or str(conf["id"]) == text or str(conf.get("manifest_no")) == text:
                return conf
        if text.isdigit():
            for conf in self.confirmations:
                if int(conf["id"]) == int(text):
                    return conf
        return None

    def _conf_detail(self, conf: dict[str, Any]) -> dict[str, Any]:
        data = dict(conf)
        data["lines"] = [dict(line) for line in conf["lines"]]
        data["rejected"] = [dict(item) for item in conf["rejected"]]
        data["dispatch_count"] = conf["dispatch_count"]
        data["download_count"] = conf["download_count"]
        return data

    def list_confirmations(self, *, subscriber: Any = None, version: Any = None,
                           batch_id: Any = None) -> list[dict[str, Any]]:
        name = None
        sub = self.resolve_subscriber(subscriber) if subscriber not in (None, "") else None
        if sub:
            name = str(sub.get("订阅方标识"))
        batch = self.resolve_batch(version=version, batch_id=batch_id) if (version or batch_id) else None
        ver = self._batch_version(batch) if batch else None
        with self._lock:
            rows = []
            for conf in self.confirmations:
                if name and conf["订阅方"] != name:
                    continue
                if ver and conf["version"] != ver:
                    continue
                rows.append(self._conf_detail(conf))
        rows.sort(key=lambda c: int(c["id"]))
        return rows

    def continue_confirmation(self, code: str) -> dict[str, Any]:
        with self._lock:
            conf = self.get_confirmation(code)
            if conf is None:
                return {"ok": False, "message": f"确认单 {code} 不存在"}
            # 断点续领：仍然是同一份确认、同一版发布、同一份清单，不重新计算资格。
            conf["continue_count"] = int(conf.get("continue_count", 0)) + 1
            if conf["delivery_state"] == "未开始":
                conf["delivery_state"] = "交付中"
            return {"ok": True, "message": f"从同一确认 {conf['code']}（清单 {conf['manifest_no']}）继续，不混入新授权数据",
                    "confirmation": self._conf_detail(conf)}

    # ------------------------------------------------------------- download

    def download(self, code: str) -> dict[str, Any]:
        """返回下载内容与元数据。首次下载生成唯一派送记录，重复下载不新增派送。"""
        with self._lock:
            conf = self.get_confirmation(code)
            if conf is None:
                return {"ok": False, "status_code": 404, "message": f"确认单 {code} 不存在"}
            first = conf["dispatch_count"] == 0
            ts = now_text()
            if first:
                dispatch = {
                    "id": self._next(), "code": self._new_code("DISP"),
                    "confirmation_code": conf["code"], "manifest_no": conf["manifest_no"],
                    "清单编号": conf["manifest_no"], "subscriber": conf["订阅方"], "订阅方": conf["订阅方"],
                    "version": conf["version"], "版本标识": conf["version"],
                    "golden_publish_id": conf.get("golden_publish_id"),
                    "region": conf["region"], "line_count": len(conf["lines"]),
                    "dispatched_at": ts, "派送时间": ts, "channel": "受控分发清单下载",
                }
                self.dispatches.append(dispatch)
                conf["dispatch_count"] = 1
                conf["first_downloaded_at"] = ts
                conf["首次领取时间"] = ts
                conf["status"] = "已领取"
                conf["delivery_state"] = "已完成"
            conf["download_count"] = int(conf.get("download_count", 0)) + 1
            conf["last_downloaded_at"] = ts
            csv_text = self._render_csv(conf)
            return {"ok": True, "first_dispatch": first, "csv": csv_text,
                    "filename": f"{conf['manifest_no']}_{conf['订阅方']}_{conf['region']}.csv",
                    "confirmation": self._conf_detail(conf)}

    def _render_csv(self, conf: dict[str, Any]) -> str:
        output = io.StringIO()
        output.write("﻿")
        headers = ["清单编号", "确认单号", "订阅方", "收件主体", "版本标识", "发布批次", "实体",
                   "记录编号", "客户名称", "归属地区", "归属依据", "权限来源", "授权单号", "授权时间",
                   "统一社会信用代码", "联系人", "联系电话"]
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for line in conf["lines"]:
            row = dict(line)
            row["确认单号"] = conf["code"]
            row["订阅方"] = conf["订阅方"]
            row["收件主体"] = conf["订阅方"]
            # CSV 公式注入防护（与通用导出保持一致）。
            for key, value in list(row.items()):
                if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
                    row[key] = "'" + value
            writer.writerow(row)
        return output.getvalue()

    # -------------------------------------------------------------- history

    def history(self, *, version: Any = None, batch_id: Any = None,
                golden_publish_id: Any = None) -> dict[str, Any]:
        batch = self.resolve_batch(version=version, batch_id=batch_id or golden_publish_id)
        ver = self._batch_version(batch)
        confs = [self._conf_detail(c) for c in self.confirmations if c["version"] == ver]
        rejected_items: list[dict[str, Any]] = []
        for conf in confs:
            for item in conf["rejected"]:
                rejected_items.append(dict(item))
        dispatches = [dict(d) for d in self.dispatches if d["version"] == ver]
        subscriber_names = sorted({c["订阅方"] for c in confs} | {r["订阅方"] for r in rejected_items})
        return {
            "ok": True, "version": ver, "batch": self._batch_brief(batch),
            "subscribers": subscriber_names,
            "deliveries": confs,
            "交付单": confs,
            "rejected_items": rejected_items,
            "被拒绝项": rejected_items,
            "dispatches": dispatches,
            "派送记录": dispatches,
            "counts": {"deliveries": len(confs), "rejected": len(rejected_items),
                       "dispatches": len(dispatches)},
        }

    def meta(self) -> dict[str, Any]:
        subscribers = [{"id": r.get("id"), "name": r.get("订阅方标识"), "status": r.get("status"),
                        "订阅实体": r.get("订阅实体")}
                       for r in store.rows("subscriber_mgr") if r.get("订阅方标识")]
        batches = [{"id": r.get("id"), "发布批次": r.get("发布批次"), "版本标识": r.get("版本标识"),
                    "实体编码": r.get("实体编码"), "status": r.get("status")}
                   for r in store.rows("golden_publish")]
        return {"regions": REGIONS, "entity": CUSTOMER_ENTITY,
                "default_version": CUSTOMER_VERSION, "subscribers": subscribers, "batches": batches}


controlled = ControlledDistributionService()
