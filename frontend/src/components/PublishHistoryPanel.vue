<template>
  <div v-if="batchId !== null" class="modal-backdrop" data-testid="claim-history-modal" @click.self="emit('close')">
    <div class="modal cd-history-modal" role="dialog" aria-label="该版本的领用历史">
      <h3 data-testid="claim-history-title">金记录版本领用历史 · 交付单与被拒绝项</h3>
      <p class="cd-hint">
        <template v-if="history">
          发布批次 {{ history.batch?.发布批次 }}｜版本
          <span class="cd-mono" data-testid="history-version">{{ history.version }}</span>
          ｜涉及订阅方：<strong data-testid="history-subscribers">{{ history.subscribers.join('、') || '—' }}</strong>
          ｜交付单 {{ history.counts.deliveries }} 份，被拒绝项 {{ history.counts.rejected }} 条，派送 {{ history.counts.dispatches }} 次
        </template>
        <template v-else>加载中…</template>
      </p>

      <p v-if="error" class="cd-msg err" role="alert">{{ error }}</p>

      <h4>交付单（受控分发清单确认）</h4>
      <table class="data-table" data-testid="history-deliveries">
        <thead>
          <tr>
            <th>交付单</th><th>订阅方</th><th>地区</th><th>清单编号</th><th>可下载行</th>
            <th>状态</th><th>派送次数</th><th>确认时间</th><th>下载</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in history?.deliveries || []" :key="d.code" :data-testid="`history-delivery-${d.code}`">
            <td><strong>{{ d.交付单名称 || d.name }}</strong><br /><span class="cd-mono">{{ d.code }}</span></td>
            <td data-testid="delivery-subscriber">{{ d.订阅方 }}</td>
            <td>{{ d.地区范围 || d.region }}</td>
            <td class="cd-mono">{{ d.manifest_no }}</td>
            <td>{{ d.lines.length }}</td>
            <td>{{ d.status }}</td>
            <td data-testid="delivery-dispatch-count">{{ d.dispatch_count }}</td>
            <td>{{ d.确认时间 || d.created_at }}</td>
            <td><a class="link" :href="downloadUrl(d.code)" :download="`${d.manifest_no}.csv`">下载</a></td>
          </tr>
          <tr v-if="history && !history.deliveries.length"><td colspan="9" class="empty-state">该版本暂无交付单</td></tr>
        </tbody>
      </table>

      <h4>被拒绝项（与交付单归属同一订阅方）</h4>
      <table class="data-table" data-testid="history-rejected">
        <thead>
          <tr><th>记录编号</th><th>客户名称</th><th>归属地区</th><th>订阅方</th><th>所属交付单</th><th>拒绝原因 / 归属依据</th></tr>
        </thead>
        <tbody>
          <tr v-for="(r, idx) in history?.rejected_items || []" :key="`${r.confirmation_code}-${r.row_id}-${idx}`"
              class="rejected-row" :data-testid="`history-rejected-${r.记录编号}`">
            <td class="cd-mono">{{ r.记录编号 }}</td>
            <td>{{ r.客户名称 }}</td>
            <td>{{ r.归属地区 }}</td>
            <td data-testid="rejected-subscriber">{{ r.订阅方 }}</td>
            <td class="cd-mono">{{ r.confirmation_code }}</td>
            <td><span class="danger">{{ r.拒绝原因 }}</span><br /><span class="cd-hint">{{ r.归属依据 }}</span></td>
          </tr>
          <tr v-if="history && !history.rejected_items.length"><td colspan="6" class="empty-state">暂无被拒绝项</td></tr>
        </tbody>
      </table>

      <h4>派送记录（重复下载同一确认不新增派送）</h4>
      <table class="data-table" data-testid="history-dispatches">
        <thead><tr><th>派送单号</th><th>确认单</th><th>订阅方</th><th>行数</th><th>派送时间</th></tr></thead>
        <tbody>
          <tr v-for="dp in history?.dispatches || []" :key="dp.code">
            <td class="cd-mono">{{ dp.code }}</td><td class="cd-mono">{{ dp.confirmation_code }}</td>
            <td>{{ dp.订阅方 }}</td><td>{{ dp.line_count }}</td><td>{{ dp.派送时间 }}</td>
          </tr>
          <tr v-if="history && !history.dispatches.length"><td colspan="5" class="empty-state">尚未发生派送（交付单还未首次下载）</td></tr>
        </tbody>
      </table>

      <div class="page-actions">
        <button class="btn" type="button" data-testid="history-refresh" @click="load">刷新核对</button>
        <button class="btn primary" type="button" data-testid="history-close" @click="emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { controlApi, downloadUrl } from '@/api/control'

const props = defineProps<{ batchId: number | string | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const history = ref<any>(null)
const error = ref('')

async function load() {
  if (props.batchId === null) return
  error.value = ''
  try {
    history.value = await controlApi.publishHistory(props.batchId)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '领用历史读取失败'
  }
}

watch(() => props.batchId, (v) => {
  if (v !== null) void load()
}, { immediate: true })

defineExpose({ load })
</script>

<style scoped>
.cd-history-modal { width: min(1080px, 97vw); }
.cd-hint { color: var(--muted, #64748b); font-size: 12.5px; line-height: 1.7; }
.cd-mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.danger { color: #b91c1c; }
.cd-msg.err { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; padding: 8px 12px; border-radius: 8px; }
h4 { margin: 14px 0 6px; font-size: 14px; }
</style>
