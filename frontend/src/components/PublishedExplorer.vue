<template>
  <div class="cd-card pe" data-testid="published-explorer">
    <h4>{{ title }}</h4>
    <p class="cd-hint">
      按收件主体、实体与地区查询已发布的实际发布行；每一行都给出归属依据，
      选择收件主体时还会即时给出领取资格。归属地区无法识别的记录会被标记为不可共享。
    </p>
    <div class="cd-form-grid">
      <label v-if="showSubscriber" class="cd-field">
        <span>收件主体（用于资格判定，可留空）</span>
        <input v-model="subscriberInput" data-testid="explorer-subscriber" placeholder="如 采购程序" @change="load" />
      </label>
      <label class="cd-field narrow">
        <span>实体</span>
        <select v-model="entity" data-testid="explorer-entity" @change="load">
          <option value="">全部实体</option>
          <option value="客户">客户</option>
        </select>
      </label>
      <label class="cd-field narrow">
        <span>地区筛选</span>
        <select v-model="region" data-testid="filter-region" aria-label="按地区筛选" @change="load">
          <option value="">全部地区</option>
          <option value="北区">北区</option><option value="南区">南区</option>
          <option value="东区">东区</option><option value="西区">西区</option>
          <option value="无法识别">无法识别</option>
        </select>
      </label>
      <label class="cd-field">
        <span>关键字（记录编号 / 客户 / 依据）</span>
        <input v-model="keyword" data-testid="filter-keyword" placeholder="如 KH-2026-001 或 北京" @keyup.enter="load" />
      </label>
      <div class="cd-actions">
        <button class="btn primary" type="button" data-testid="explorer-query-btn" @click="load">查询 / 筛选</button>
        <button class="btn ghost" type="button" data-testid="explorer-reset-btn" @click="reset">重置</button>
      </div>
    </div>

    <p v-if="message" class="cd-msg" :class="ok ? 'ok' : 'err'" data-testid="explorer-message">{{ message }}</p>

    <table class="data-table" data-testid="published-row-table">
      <thead>
        <tr>
          <th>记录编号</th><th>客户名称</th><th>实体</th><th>版本</th><th>归属地区</th>
          <th>归属依据</th>
          <th v-if="effectiveSubscriber">{{ effectiveSubscriber }}资格</th>
          <th>管理员操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id" :data-testid="`published-row-${r.记录编号}`">
          <td class="cd-mono">{{ r.记录编号 }}</td>
          <td>{{ r.客户名称 }}</td>
          <td>{{ r.实体名称 }}</td>
          <td class="cd-mono">{{ r.版本标识 }}</td>
          <td><span class="cd-badge" :class="r.地区可识别 ? 'done' : 'revoked'">{{ r.归属地区 }}</span></td>
          <td data-testid="row-basis">{{ r.归属依据 }}</td>
          <td v-if="effectiveSubscriber">
            <span v-if="r.资格判定" :class="r.资格判定.eligible ? 'ok-text' : 'danger'">
              {{ r.资格判定.eligible ? '可领取' : r.资格判定.reason }}
            </span>
            <span v-else>—</span>
          </td>
          <td>
            <button class="link" type="button" :data-testid="`attribution-btn-${r.id}`" @click="toggle(r.id)">
              调整数据归属
            </button>
            <div v-if="editId === r.id" class="cd-attribution-editor" :data-testid="`attribution-editor-${r.id}`">
              <select v-model="formRegion" :data-testid="`attribution-region-${r.id}`" aria-label="新归属地区">
                <option value="北区">北区</option><option value="南区">南区</option>
                <option value="东区">东区</option><option value="西区">西区</option>
                <option value="无法识别">无法识别（不可共享）</option>
              </select>
              <input v-model="formBasis" :data-testid="`attribution-basis-input-${r.id}`" placeholder="调整后的归属依据" />
              <button class="btn primary" type="button" :data-testid="`save-attribution-${r.id}`" @click="save(r.id)">保存归属</button>
              <button class="btn ghost" type="button" @click="editId = null">取消</button>
            </div>
          </td>
        </tr>
        <tr v-if="!rows.length"><td :colspan="effectiveSubscriber ? 8 : 7" class="empty-state">没有符合筛选条件的发布数据</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { controlApi } from '@/api/control'

const props = withDefaults(defineProps<{
  subscriber?: string
  version?: string
  title?: string
  showSubscriber?: boolean
}>(), {
  subscriber: '',
  version: '',
  title: '发布数据查询与筛选（每条数据的归属依据可查，管理员可调整数据归属）',
  showSubscriber: false,
})

const rows = ref<any[]>([])
const region = ref('')
const entity = ref('')
const keyword = ref('')
const subscriberInput = ref(props.subscriber)
const editId = ref<number | string | null>(null)
const formRegion = ref('北区')
const formBasis = ref('')
const message = ref('')
const ok = ref(true)

const effectiveSubscriber = computed(() => (props.subscriber || subscriberInput.value || '').trim())

watch(() => props.subscriber, (v) => { subscriberInput.value = v })
watch(() => props.version, () => { void load() })

async function load() {
  try {
    const d = await controlApi.publishedRows({
      subscriber: effectiveSubscriber.value || undefined,
      version: props.version || undefined,
      entity: entity.value || undefined,
      region: region.value || undefined,
      keyword: keyword.value || undefined,
    })
    rows.value = d.items || []
  } catch (e) {
    message.value = e instanceof Error ? e.message : '发布数据查询失败'
    ok.value = false
  }
}

function reset() {
  region.value = ''
  entity.value = ''
  keyword.value = ''
  void load()
}

function toggle(id: number | string) {
  editId.value = editId.value === id ? null : id
  const row = rows.value.find((r) => r.id === id)
  if (row) {
    formRegion.value = row.归属地区 === '无法识别' ? '无法识别' : row.归属地区
    formBasis.value = row.归属依据
  }
}

async function save(id: number | string) {
  try {
    const d = await controlApi.adjustAttribution(id, { region: formRegion.value, basis: formBasis.value })
    message.value = d.message || (d.ok === false ? '归属调整失败' : '已调整数据归属')
    ok.value = d.ok !== false
    editId.value = null
    await load()
  } catch (e) {
    message.value = e instanceof Error ? e.message : '归属调整失败'
    ok.value = false
  }
}

defineExpose({ load })
onMounted(load)
</script>

<style scoped>
.cd-hint { color: var(--muted, #64748b); font-size: 12.5px; line-height: 1.7; margin: 4px 0 10px; }
.cd-form-grid { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.cd-field { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; flex: 1 1 200px; }
.cd-field.narrow { flex: 0 1 150px; }
.cd-field input, .cd-field select { padding: 7px 9px; border: 1px solid var(--border, #cbd5e1); border-radius: 6px; font-size: 13px; background: #fff; }
.cd-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.cd-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.cd-badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #e2e8f0; }
.cd-badge.done { background: #dcfce7; color: #166534; }
.cd-badge.revoked { background: #fee2e2; color: #991b1b; }
.danger { color: #b91c1c; }
.ok-text { color: #15803d; }
.cd-attribution-editor { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; min-width: 250px; }
.cd-attribution-editor input, .cd-attribution-editor select { padding: 5px 7px; border: 1px solid var(--border, #cbd5e1); border-radius: 6px; }
.cd-msg { padding: 7px 10px; border-radius: 8px; font-size: 13px; margin: 8px 0; }
.cd-msg.ok { background: #ecfdf5; color: #065f46; }
.cd-msg.err { background: #fef2f2; color: #991b1b; }
</style>
