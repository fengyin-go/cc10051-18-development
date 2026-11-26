import { createRouter, createWebHistory } from 'vue-router'

import ControlledDistributionView from '@/views/ControlledDistributionView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 受控领用工作台的独立直达地址（与下游订阅方页内嵌的是同一组件）。
    { path: '/controlled_distribution', name: 'controlled-distribution', component: ControlledDistributionView },
    { path: '/controlled-distribution', component: ControlledDistributionView },
    { path: '/claims', component: ControlledDistributionView },
    { path: '/distribution', component: ControlledDistributionView },
    { path: '/subscriber_mgr/claim', component: ControlledDistributionView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
