# 主数据治理与参考数据管理平台

覆盖主数据抽取、标准化清洗、去重合并、金记录发布与下游订阅分发的治理平台

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8021/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5201/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8021`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 源系统登记 | `source_system` | 源系统 | 系统标识、系统名称、数据域 |
| 主数据实体 | `entity_model` | 实体定义 | 实体编码、实体名称、唯一键规则 |
| 记录抽取作业 | `record_extract` | 抽取作业 | 作业名称、源系统、实体编码 |
| 标准化清洗 | `std_cleanse` | 清洗规则 | 规则名称、实体编码、清洗阶段 |
| 重复检测器 | `dup_detect` | 检测结果 | 检测批次、实体编码、候选组数 |
| 金记录合并 | `golden_merge` | 合并任务 | 合并任务、实体编码、候选组 |
| 金记录发布 | `golden_publish` | 发布批次 | 发布批次、实体编码、金记录数 |
| 下游订阅方 | `subscriber_mgr` | 订阅方 | 订阅方标识、订阅实体、分发格式 |
| 分发任务 | `dist_task` | 分发批次 | 分发批次、订阅方、记录范围 |
| 血缘关系图 | `lineage_graph` | 血缘边 | 血缘边标识、上游节点、下游节点 |
| 质量规则库 | `quality_rule` | 质量规则 | 规则名称、实体编码、检查维度 |
| 质量报告 | `quality_result` | 质量结果 | 报告批次、实体编码、检查总数 |
| 合并复核队列 | `merge_review` | 复核记录 | 记录编号、候选组、复核结论 |
| 版本回滚器 | `version_rollback` | 回滚任务 | 回滚任务、目标版本、回滚原因 |
| 同步游标 | `sync_cursor` | 游标记录 | 源系统、实体编码、游标值 |
| 标识交叉映射 | `id_cross_map` | 交叉映射 | 映射批次、源系统标识、金记录标识 |
| 分发回执中心 | `dist_receipt` | 回执记录 | 回执编号、分发批次、订阅方 |
| 实体变更审批 | `model_change` | 变更单 | 变更单号、实体编码、变更内容 |
| 治理看板数据 | `stats_overview` | 统计快照 | 统计时间、实体编码、金记录数 |
| 参考数据管理 | `ref_data_mgr` | 参考数据集 | 数据集编码、数据集名称、码值条目 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 按授权地区领用金记录（受控分发清单）

在「下游订阅方」页顶部的 **按授权地区领用金记录 · 受控分发清单** 工作台完成，
「金记录发布」页每行有 **领用历史**，并内嵌发布数据查询/归属调整。

业务规则（由 `app/services/controlled_distribution.py` 服务端判定）：

- 领用必须指定 **收件主体（订阅方）+ 发布批次/版本 + 地区范围**，先预览再确认领取。
- 只有 **订阅了对应实体** 且 **持有该行归属地区有效授权** 的收件方，该行才可交付；
  未订阅实体 / 无该地区授权（含授权已撤销）分别给出拒绝原因。
- **归属地区无法识别的行一律拒绝，不会被当成共享行放行**。
- 确认后生成唯一 **确认单号 + 清单编号**，冻结唯一一版发布与一份清单（行内容、归属依据、
  权限来源/授权单号均入快照）；断点后用同一确认「继续领取」，重复下载同一确认 **只产生一次派送**。
- 地区授权的授予/撤销全程留痕，`撤销时间(reported as 撤销时间 / revoked_at)` 即权限撤去时点。
- 发布端 **领用历史** 按版本汇总交付单、被拒绝项与派送记录，均可核对到同一订阅方。

主要接口（同时挂在 `/api/distribution`、`/api/claims`、`/api/region-grants` 等别名下）：

```text
GET  /api/controlled-distribution/meta
GET  /api/controlled-distribution/published-rows   # 发布数据查询/筛选+资格判定
POST /api/controlled-distribution/preview          # 预览受控分发清单（返回 preview_id）
POST /api/controlled-distribution/claims           # 确认领取（可带 preview_id 计算变化影响）
GET  /api/controlled-distribution/claims[/{code}]
POST /api/controlled-distribution/claims/{code}/continue
GET  /api/controlled-distribution/claims/{code}/download[?format=json]
GET/POST /api/controlled-distribution/grants       # 地区授权/撤销（留撤销时点）
POST .../published-rows/{id}/attribution           # 管理员调整数据归属
GET  /api/golden_publish/{id}/claim-history        # 发布版本的交付单+被拒绝项
```

内置剧本数据：订阅方 **采购程序**（订阅实体「客户」，持北区授权，另有一条已撤销的西区授权）、
发布版本 `v-customer-2026q3` 的 8 条客户行（含 1 条地区无法识别行），以及一份
**尚未领取的「北区客户交付」** 确认单 `CONF-PROC-BEI-0001`（清单 `MAN-PROC-BEI-0001`，3 行）。

领域：数据工程
子方向：数仓与数据湖
