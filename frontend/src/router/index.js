import { createRouter, createWebHashHistory } from 'vue-router'
import { defineAsyncComponent } from 'vue'
import IndexPage from '../views/IndexPage.vue'

// 路由级代码分割：除首屏 IndexPage 外，其余视图均改为异步组件按需加载，
// 把单块 409KB 主包拆成多个小 chunk，显著降低首屏 JS 体积（d3 等已在组件内动态 import）。
const ReaderPage = defineAsyncComponent(() => import('../views/ReaderPage.vue'))
const ScriptsPage = defineAsyncComponent(() => import('../views/ScriptsPage.vue'))
const FoldersPage = defineAsyncComponent(() => import('../views/FoldersPage.vue'))
const FolderDetailPage = defineAsyncComponent(() => import('../views/FolderDetailPage.vue'))
const GraphPage = defineAsyncComponent(() => import('../views/GraphPage.vue'))
const LearningPathPage = defineAsyncComponent(() => import('../views/LearningPathPage.vue'))
const StudyPlanPage = defineAsyncComponent(() => import('../views/StudyPlanPage.vue'))
const AgentPage = defineAsyncComponent(() => import('../views/AgentPage.vue'))

const routes = [
  { path: '/', name: 'index', component: IndexPage },
  // 全屏阅读页：DetailPanel"全屏查看"在新标签打开 #/reader/{id}
  { path: '/reader/:id', name: 'reader', component: ReaderPage },
  { path: '/scripts', name: 'scripts', component: ScriptsPage },
  { path: '/folders', name: 'folders', component: FoldersPage },
  { path: '/folders/:name', name: 'folder-detail', component: FolderDetailPage },
  { path: '/graph', name: 'graph', component: GraphPage },
  { path: '/learning', name: 'learning', component: LearningPathPage },
  // 动态学习计划页：分时间维度（今日/明日/本周/本月）的 AI 生成计划
  { path: '/study-plan', name: 'study-plan', component: StudyPlanPage },
  { path: '/agent', name: 'agent', component: AgentPage },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
