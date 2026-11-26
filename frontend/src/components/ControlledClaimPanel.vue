<template>
  <section
    class="cd-panel"
    data-testid="controlled-claim-panel"
    data-module="subscriber_mgr"
    aria-label="按授权地区领用金记录"
  >
    <header class="cd-head">
      <h3>按授权地区领用金记录 · 受控分发清单</h3>
      <p class="cd-hint">
        选择<strong>收件主体（订阅方）</strong>、<strong>发布批次</strong>与<strong>地区范围</strong>后先预览；
        服务端判定订阅资格并生成受控分发清单。只有订阅了对应实体且享有该地区权限的收件方才能领取该行；
        <strong>归属地区无法识别的记录不会被当成共享行</strong>。一笔交付只引用一版发布和一份清单，
        断开后可从同一确认继续，重复下载同一确认不新增派送。
      </p>
    </header>

    <p v-if="message" class="cd-message" :class="messageOk ? 'ok' : 'err'" role="status" data-testid="control-message">
      {{ message }}
    </p>

    <!-- ① 领用条件 -->
    <div class="cd-card" data-testid="claim-form">
      <h4>① 选择收件主体、发布批次与地区范围</h4>
      <div class="cd-form-grid">
        <label class="cd-field">
          <span>收件主体 / 订阅方</span>
          <select v-model="form.subscriber" data-testid="claim-subscriber-select" aria-label="收件主体">
            <option v-for="s in meta.subscribers" :key="s.id" :value="String(s.name)">
              {{ s.name }}（{{ s.status }}）
            </option>
          </select>
        </label>
        <label class="cd-field">
          <span>发布批次 / 版本</span>
          <select v-model="form.version" data-testid="claim-batch-select" aria-label="发布批次">
            <option v-for="b in meta.batches" :key="String(b.id)" :value="String(b.版本标识)">
              {{ b.发布批次 }} · {{ b.版本标识 }} · {{ b.实体编码 }}
            </option>
          </select>
        </label>
        <label class="cd-field narrow">
          <span>实体</span>
          <input v-model="form.entity" data-testid="claim-entity" aria-label="实体" />
        </label>
        <label class="cd-field narrow">
          <span>地区范围</span>
          <select v-model="form.region" data-testid="claim-region-select" aria-label="地区范围">
            <option value="北区">北区</option>
            <option value="南区">南区</option>
            <option value="东区">东区</option>
            <option value="西区">西区</option>
            <option value="全部地区">全部地区</option>
          </select>
        </label>
        <div class="cd-actions">
          <button class="btn primary" type="button" data-testid="preview-btn" @click="runPreview">
            生成预览 / 预览受控分发清单
          </button>
          <button class="btn" type="button" data-testid="query-published-btn" @click="scrollExplorer">
            查询发布数据
          </button>
        </div>
      </div>
    </div>

    <!-- 已安排的交付单（含种子「北区客户交付」） -->
    <div class="cd-card" data-testid="delivery-list">
      <h4>② 交付单与确认（先前已安排、尚未领取的交付从这里继续）</h4>
      <p class="cd-hint">
        交付单冻结唯一版本与唯一清单；点击「继续领取」仍回到同一确认，下载同一批行。
        同一确认重复下载只增加下载次数，<strong>不新增派送</strong>。
      </p>
      <table class="data-table" data-testid="confirmation-table">
        <thead>
          <tr>
            <th>交付单 / 确认号</th><th>收件主体</th><th>地区</th><th>发布版本</th><th>清单编号</th>
            <th>可下载行</th><th>状态</th><th>派送/下载</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in claims" :key="c.code" :data-testid="`delivery-row-${c.code}`">
            <td>
              <strong>{{ c.交付单名称 || c.name }}</strong><br />
              <span class="cd-mono">{{ c.code }}</span>
            </td>
            <td>{{ c.订阅方 }}</td>
            <td>{{ c.地区范围 || c.region }}</td>
            <td class="cd-mono">{{ c.版本标识 }}</td>
            <td class="cd-mono">{{ c.清单编号 }}</td>
            <td>{{ c.lines.length }}</td>
            <td>
              <span class="cd-badge" :class="c.status === '已领取' ? 'done' : 'pending'">{{ c.status }}</span>
              <span v-if="c.delivery_state === '交付中'" class="cd-badge warn">交付中断·可续领</span>
            </td>
            <td>派送 {{ c.dispatch_count }} 次 / 下载 {{ c.download_count }} 次</td>
            <td class="cd-row-actions">
              <button class="link" type="button" :data-testid="`continue-${c.code}`" @click="continueClaim(c.code)">
                继续领取
              </button>
              <a
                class="link cd-download-link"
                :href="downloadUrl(c.code)"
                :data-testid="`download-${c.code}`"
                :download="`${c.清单编号}.csv`"
                @click="scheduleRefresh"
              >下载受控清单</a>
              <button class="link" type="button" :data-testid="`detail-${c.code}`" @click="openDetail(c.code)">
                归属依据/详情
              </button>
            </td>
          </tr>
          <tr v-if="!claims.length"><td colspan="9" class="empty-state">暂无交付单，可在上方生成预览后确认领取</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ③ 地区授权 -->
    <div class="cd-card" data-testid="grant-panel">
      <h4>③ 收件主体的授权地区（授予 / 撤去权限时点可核对）</h4>
      <div class="cd-grant-bar">
        <label class="cd-field narrow">
          <span>选择地区</span>
          <select v-model="grantRegion" data-testid="grant-region-select" aria-label="授权地区">
            <option value="北区">北区</option>
            <option value="南区">南区</option>
            <option value="东区">东区</option>
            <option value="西区">西区</option>
          </select>
        </label>
        <button class="btn" type="button" data-testid="grant-btn" @click="changeGrant('grant')">授予地区授权</button>
        <button class="btn ghost danger" type="button" data-testid="revoke-btn" aria-label="撤销授权" @click="changeGrant('revoke')">撤销授权</button>
        <span class="cd-hint">先在左侧选择地区；撤去后会记录「撤销时间」作为权限失效时点，可回查核对。</span>
      </div>
      <table class="data-table" data-testid="grant-table">
        <thead>
          <tr><th>授权单号</th><th>地区</th><th>状态</th><th>授权来源 / 权限来源</th><th>授权时间</th><th>撤销时间（撤去时点）</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="g in grants" :key="g.id" :data-testid="`grant-row-${g.id}`">
            <td class="cd-mono">{{ g.授权单号 }}</td>
            <td>{{ g.地区 }}</td>
            <td><span class="cd-badge" :class="g.状态 === '有效' ? 'done' : 'revoked'">{{ g.状态 }}</span></td>
            <td>{{ g.授权来源 }}</td>
            <td>{{ g.授权时间 }}</td>
            <td :data-testid="`revoked-at-${g.id}`">{{ g.撤销时间 || '—' }}</td>
            <td>
              <button
                v-if="g.状态 === '有效'"
                class="link danger"
                type="button"
                :data-testid="`revoke-grant-${g.id}`"
                :aria-label="`撤销${g.地区}授权`"
                @click="revokeGrant(g.id)"
              >撤销{{ g.地区 }}授权</button>
              <span v-else class="cd-hint">已撤去</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ④ 预览结果 + 影响提示 + 确认领取 -->
    <div v-if="preview" class="cd-card" data-testid="preview-panel">
      <h4>④ 受控分发清单预览（按当前授权实时判定）</h4>
      <p class="cd-hint">
        预览编号 <span class="cd-mono" data-testid="preview-id">{{ preview.preview_id }}</span>
        ｜可交付 <strong data-testid="preview-eligible-count">{{ preview.counts.eligible }}</strong> 条，
        被拒绝 <strong data-testid="preview-rejected-count">{{ preview.counts.rejected }}</strong> 条，
        不在本地区范围 {{ preview.counts.out_of_scope }} 条。
      </p>

      <div v-if="impact" class="cd-impact" role="alert" data-testid="claim-impact">
        <strong>授权/归属变化对本次领取的影响：</strong>
        <p data-testid="impact-summary">{{ impact.summary }}</p>
        <ul v-if="impact.removed.length" data-testid="impact-removed">
          <li v-for="x in impact.removed" :key="`rm-${x.row_id}`" class="removed">
            移出：{{ x.记录编号 }} {{ x.客户名称 }}（{{ x.reason || '已失去资格' }}）
          </li>
        </ul>
        <ul v-if="impact.added.length" data-testid="impact-added">
          <li v-for="x in impact.added" :key="`add-${x.row_id}`" class="added">
            新纳入：{{ x.记录编号 }} {{ x.客户名称 }}（{{ x.归属地区 }}）
          </li>
        </ul>
      </div>

      <div class="cd-actions">
        <button class="btn primary" type="button" data-testid="confirm-claim-btn" @click="confirmClaim">
          确认领取（冻结这份清单并生成交付单）
        </button>
        <span class="cd-hint">先预览再改动授权后点击领取，页面会指出变化影响了哪一部分记录。</span>
      </div>

      <h5>可交付行（含每条数据的归属依据与本次权限来源）</h5>
      <table class="data-table" data-testid="preview-eligible-table">
        <thead>
          <tr><th>记录编号</th><th>客户名称</th><th>归属地区</th><th>归属依据</th><th>权限来源</th><th>授权单号</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in preview.eligible" :key="`e-${r.row_id}`" :data-testid="`eligible-row-${r.记录编号}`">
            <td class="cd-mono">{{ r.记录编号 }}</td>
            <td>{{ r.客户名称 }}</td>
            <td>{{ r.归属地区 }}</td>
            <td data-testid="attribution-basis">{{ r.归属依据 }}</td>
            <td>{{ r.权限来源 }}</td>
            <td class="cd-mono">{{ r.授权单号 }}</td>
          </tr>
          <tr v-if="!preview.eligible.length"><td colspan="6" class="empty-state">当前没有可交付行（可能授权已被撤去）</td></tr>
        </tbody>
      </table>

      <h5>被拒绝项（服务端资格判定）</h5>
      <table class="data-table" data-testid="preview-rejected-table">
        <thead>
          <tr><th>记录编号</th><th>客户名称</th><th>归属地区</th><th>拒绝原因</th><th>归属依据</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in preview.rejected" :key="`r-${r.row_id}`" class="rejected-row" :data-testid="`rejected-row-${r.记录编号}`">
            <td class="cd-mono">{{ r.记录编号 }}</td>
            <td>{{ r.客户名称 }}</td>
            <td>{{ r.归属地区 }}</td>
            <td class="danger" data-testid="reject-reason">{{ r.reason }}</td>
            <td>{{ r.归属依据 }}</td>
          </tr>
        </tbody>
      </table>

      <details class="cd-scope">
        <summary>不在本次「{{ preview.region }}」地区范围的记录（{{ preview.out_of_scope.length }}）</summary>
        <ul>
          <li v-for="r in preview.out_of_scope" :key="`o-${r.row_id}`">
            {{ r.记录编号 }} {{ r.客户名称 }} —— {{ r.reason }}
          </li>
        </ul>
      </details>
    </div>

    <!-- ⑤ 发布数据查询与筛选 + 管理员调整归属（复用组件） -->
    <PublishedExplorer :subscriber="form.subscriber" :version="form.version" show-subscriber />

    <!-- 详情弹窗：冻结行 + 被拒绝项 + 依据回查 -->
    <div v-if="detail" class="modal-backdrop" data-testid="detail-modal" @click.self="detail = null">
      <div class="modal cd-modal-wide" role="dialog" aria-label="交付单详情与归属依据">
        <h3>交付单 {{ detail.交付单名称 || detail.name }}</h3>
        <p class="cd-hint">
          确认号 <span class="cd-mono">{{ detail.code }}</span>
          ｜清单 <span class="cd-mono">{{ detail.manifest_no }}</span>
          ｜版本 <span class="cd-mono">{{ detail.版本标识 }}</span>
          ｜收件主体 {{ detail.订阅方 }}｜地区 {{ detail.地区范围 || detail.region }}
          ｜状态 {{ detail.status }}｜派送 {{ detail.dispatch_count }} 次
        </p>
        <p class="cd-hint">完成领取后，每行的归属依据与权限来源仍可在此回查；清单为确认时冻结的快照。</p>
        <div v-if="detail.impact && detail.impact.affected" class="cd-impact" data-testid="detail-impact">
          <strong>本次确认相对预览的变化影响：</strong>{{ detail.impact.summary }}
        </div>
        <h5>可下载发布行（{{ detail.lines.length }}）</h5>
        <table class="data-table">
          <thead><tr><th>记录编号</th><th>客户名称</th><th>地区</th><th>归属依据</th><th>权限来源</th></tr></thead>
          <tbody>
            <tr v-for="l in detail.lines" :key="l.row_id">
              <td class="cd-mono">{{ l.记录编号 }}</td><td>{{ l.客户名称 }}</td><td>{{ l.归属地区 }}</td>
              <td>{{ l.归属依据 }}</td><td>{{ l.权限来源 }}</td>
            </tr>
            <tr v-if="!detail.lines.length"><td colspan="5" class="empty-state">该确认单没有可交付行</td></tr>
          </tbody>
        </table>
        <h5>被拒绝项（{{ detail.rejected.length }}，同属 {{ detail.订阅方 }}）</h5>
        <table class="data-table">
          <thead><tr><th>记录编号</th><th>客户名称</th><th>地区</th><th>拒绝原因</th></tr></thead>
          <tbody>
            <tr v-for="r in detail.rejected" :key="r.row_id">
              <td class="cd-mono">{{ r.记录编号 }}</td><td>{{ r.客户名称 }}</td><td>{{ r.归属地区 }}</td>
              <td class="danger">{{ r.拒绝原因 }}</td>
            </tr>
          </tbody>
        </table>
        <div class="page-actions">
          <a class="btn primary" :href="downloadUrl(detail.code)" :download="`${detail.清单编号}.csv`" data-testid="detail-download">下载这份清单（同一确认）</a>
          <button class="btn" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { controlApi, downloadUrl } from '@/api/control'
import PublishedExplorer from '@/components/PublishedExplorer.vue'

const message = ref('')
const messageOk = ref(true)

const meta = ref<any>({ subscribers: [], batches: [], regions: [] })
const form = reactive<{ subscriber: string; version: string; entity: string; region: string }>({
  subscriber: '采购程序',
  version: 'v-customer-2026q3',
  entity: '客户',
  region: '北区',
})
const grantRegion = ref('北区')
const grants = ref<any[]>([])
const claims = ref<any[]>([])
const preview = ref<any>(null)
const impact = ref<any>(null)
const detail = ref<any>(null)

function flash(text: string, ok = true) {
  message.value = text
  messageOk.value = ok
}

async function loadMeta() {
  try {
    meta.value = await controlApi.meta()
    const hasProc = meta.value.subscribers?.some((s: any) => s.name === '采购程序')
    if (!hasProc && meta.value.subscribers?.length) form.subscriber = String(meta.value.subscribers[0].name)
    const hasVersion = meta.value.batches?.some((b: any) => b.版本标识 === form.version)
    if (!hasVersion && meta.value.batches?.length) form.version = String(meta.value.batches[0].版本标识)
  } catch (e) {
    flash(e instanceof Error ? e.message : '元数据读取失败', false)
  }
}

async function loadGrants() {
  try {
    const d = await controlApi.grants(form.subscriber)
    grants.value = d.items || []
  } catch { /* 保留空表 */ }
}

async function loadClaims() {
  try {
    const d = await controlApi.claims({ subscriber: form.subscriber })
    claims.value = d.items || []
  } catch { /* ignore */ }
}

function scrollExplorer() {
  document.querySelector('[data-testid="published-explorer"]')?.scrollIntoView({ behavior: 'smooth' })
}

async function runPreview() {
  impact.value = null
  try {
    await loadMeta()
    const d = await controlApi.preview({
      subscriber: form.subscriber,
      version: form.version,
      region: form.region,
      entity: form.entity,
    })
    if (d.ok === false) {
      flash(d.message || '预览失败', false)
      return
    }
    preview.value = d
    flash(`预览完成：可交付 ${d.counts.eligible} 条，被拒绝 ${d.counts.rejected} 条`)
  } catch (e) {
    flash(e instanceof Error ? e.message : '预览请求失败', false)
  }
}

async function confirmClaim() {
  try {
    const d = await controlApi.createClaim({
      subscriber: form.subscriber,
      version: form.version,
      region: form.region,
      entity: form.entity,
      preview_id: preview.value?.preview_id,
    })
    // 无论是否还具备资格，只要服务端给出了预览后的变化，就先把受影响部分指出来。
    impact.value = d.impact || null
    if (!d.ok) {
      flash(d.message || '领取失败', false)
      if (d.evaluation) {
        preview.value = {
          ...(preview.value || {}),
          ...d.evaluation,
          preview_id: preview.value?.preview_id,
        }
      }
      return
    }
    flash(d.message, true)
    await Promise.all([loadClaims(), loadGrants()])
  } catch (e) {
    flash(e instanceof Error ? e.message : '领取请求失败', false)
  }
}

async function changeGrant(action: 'grant' | 'revoke') {
  try {
    const d = await controlApi.changeGrant({
      subscriber: form.subscriber,
      region: grantRegion.value,
      action,
    })
    flash(d.message, d.ok !== false)
    await loadGrants()
    // 授权变化后，如果已经有预览，自动刷新预览但保留旧 preview_id 供领取时对比影响。
    if (preview.value) {
      const oldPreviewId = preview.value.preview_id
      const fresh = await controlApi.preview({
        subscriber: form.subscriber, version: form.version, region: form.region,
      })
      // 仍然把领取请求关联到「变化前」的预览编号，由服务端对比影响。
      preview.value = { ...fresh, preview_id: oldPreviewId, counts: fresh.counts,
        eligible: fresh.eligible, rejected: fresh.rejected, out_of_scope: fresh.out_of_scope }
    }
  } catch (e) {
    flash(e instanceof Error ? e.message : '授权调整失败', false)
  }
}

async function revokeGrant(id: number | string) {
  try {
    const d = await controlApi.revokeGrant(id, {})
    flash(d.message, d.ok !== false)
    await loadGrants()
  } catch (e) {
    flash(e instanceof Error ? e.message : '撤销授权失败', false)
  }
}

async function continueClaim(code: string) {
  try {
    const d = await controlApi.continueClaim(code)
    flash(d.message, d.ok !== false)
    const full = await controlApi.claim(code)
    if (full.ok) detail.value = full.confirmation
    await loadClaims()
  } catch (e) {
    flash(e instanceof Error ? e.message : '继续领取失败', false)
  }
}

async function openDetail(code: string) {
  try {
    const d = await controlApi.claim(code)
    if (d.ok) detail.value = d.confirmation
  } catch (e) {
    flash(e instanceof Error ? e.message : '详情读取失败', false)
  }
}

function scheduleRefresh() {
  window.setTimeout(() => void loadClaims(), 900)
}

/** 供父组件行内按钮调用：定位到该订阅方并发起预览。 */
function startForSubscriber(nameOrId: string | number, focusGrant = false) {
  const match = meta.value.subscribers?.find(
    (s: any) => String(s.id) === String(nameOrId) || s.name === nameOrId || s.name?.includes(String(nameOrId)),
  )
  form.subscriber = match ? String(match.name) : String(nameOrId)
  impact.value = null
  void loadGrants()
  void loadClaims()
  const root = document.querySelector('[data-testid="controlled-claim-panel"]')
  root?.scrollIntoView({ behavior: 'smooth' })
  if (focusGrant) {
    window.setTimeout(() => {
      document.querySelector('[data-testid="grant-panel"]')?.scrollIntoView({ behavior: 'smooth' })
    }, 250)
  }
}

defineExpose({ startForSubscriber, refreshMeta: loadMeta })

onMounted(async () => {
  await loadMeta()
  await Promise.all([loadGrants(), loadClaims()])
})
</script>

<style scoped>
.cd-panel { margin: 14px 0 28px; display: flex; flex-direction: column; gap: 12px; }
.cd-head h3 { margin: 0 0 6px; font-size: 18px; }
.cd-hint { color: var(--muted, #64748b); font-size: 12.5px; line-height: 1.7; margin: 4px 0; }
.cd-card { background: #f8fafc; border: 1px solid var(--border, #e2e8f0); border-radius: 10px; padding: 14px 16px; }
.cd-card h4 { margin: 0 0 10px; font-size: 15px; }
.cd-card h5 { margin: 14px 0 6px; font-size: 13.5px; }
.cd-form-grid { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.cd-field { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; flex: 1 1 220px; }
.cd-field.narrow { flex: 0 1 150px; }
.cd-field input, .cd-field select { padding: 7px 9px; border: 1px solid var(--border, #cbd5e1); border-radius: 6px; font-size: 13px; background: #fff; }
.cd-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.cd-row-actions { display: flex; gap: 10px; flex-wrap: wrap; white-space: nowrap; }
.cd-message { padding: 9px 12px; border-radius: 8px; font-size: 13.5px; }
.cd-message.ok { background: #ecfdf5; border: 1px solid #6ee7b7; color: #065f46; }
.cd-message.err { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; }
.cd-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #e2e8f0; }
.cd-badge.done { background: #dcfce7; color: #166534; }
.cd-badge.pending { background: #fef9c3; color: #854d0e; }
.cd-badge.warn { background: #ffedd5; color: #9a3412; }
.cd-badge.revoked { background: #fee2e2; color: #991b1b; }
.cd-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.cd-grant-bar { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 10px; }
.cd-impact { border: 1px solid #f59e0b; background: #fffbeb; border-radius: 8px; padding: 10px 14px; margin: 10px 0; font-size: 13.5px; }
.cd-impact ul { margin: 6px 0; padding-left: 20px; }
.cd-impact .removed { color: #b91c1c; }
.cd-impact .added { color: #15803d; }
.danger { color: #b91c1c; }
.ok-text { color: #15803d; }
.link.danger { color: #b91c1c; }
.btn.danger { color: #b91c1c; border-color: #fca5a5; }
.cd-scope { margin-top: 10px; font-size: 13px; }
.cd-attribution-editor { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; min-width: 240px; }
.cd-attribution-editor input, .cd-attribution-editor select { padding: 5px 7px; border: 1px solid var(--border, #cbd5e1); border-radius: 6px; }
.cd-modal-wide { width: min(960px, 96vw); }
.cd-download-link { margin-right: 2px; }
</style>
