<template>
  <section class="page" data-module="controlled_distribution">
    <header class="page-head">
      <div>
        <h2>按授权地区领用金记录 · 受控分发</h2>
        <p class="page-desc">下游订阅方按发布批次与授权地区领用，服务端判定资格并出具受控分发清单。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/subscriber_mgr">返回下游订阅方</RouterLink>
      </div>
    </header>
    <ControlledClaimPanel />
  </section>
</template>

<script setup lang="ts">
import ControlledClaimPanel from '@/components/ControlledClaimPanel.vue'
</script>
