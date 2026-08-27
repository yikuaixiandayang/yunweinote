import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentRecommendPath } from '../api'
import { useUserDataStore } from './userData'

/**
 * 动态学习计划 store（联动版 v2）。
 *
 * 数据源是后端 user_data.json：
 * - studyPlan     —— 计划（路径的投影，任务带 pathStepId）
 * - recommendPath —— 学习路径（唯一事实来源，步骤状态只存这一份）
 *
 * 走独立端点，不塞进 /api/data 主数据流。
 * AI 不可用时 generate 返回 ok=false + 旧 plan；规则降级时 degraded=true（顺序仍正确）。
 */
export const useStudyPlanStore = defineStore('studyPlan', () => {
  const plan = ref(null)
  const path = ref(null)        // recommendPath：steps[] + pathVersion
  const loading = ref(false)
  const error = ref(null)
  const degraded = ref(false)   // true = 规则模式（AI 拆解不可用，关键词匹配）

  async function load() {
    error.value = null
    try {
      const res = await fetch('/api/agent/study-plan')
      const data = await res.json()
      plan.value = data.plan
    } catch (e) {
      error.value = e.message
    }
  }

  /** 路径地图（带派生进度 progress "x/y"） */
  async function loadPath() {
    try {
      const res = await fetch('/api/agent/study-path')
      const data = await res.json()
      path.value = data.path && data.path.steps ? data.path : null
    } catch {
      path.value = null
    }
  }

  /**
   * 生成/刷新计划（联动版）。
   * 成功后同步 plan + path（步骤状态可能变化），degraded 提示规则模式。
   */
  async function generate(goal = '', feedback = '') {
    loading.value = true
    error.value = null
    try {
      const res = await fetch('/api/agent/study-plan/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, feedback }),
      })
      const data = await res.json()
      if (data.ok) {
        plan.value = data.plan
        if (data.path) path.value = data.path
        degraded.value = !!data.degraded
      } else {
        // 无路径 / 路径全完成 / 异常：保持旧计划
        if (data.plan) plan.value = data.plan
        error.value = data.error || '生成失败'
      }
      return data
    } catch (e) {
      error.value = e.message
      return { ok: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  /**
   * 任务反馈 + 回流路径（方向 B）+ 回流已读状态（P3.1 闭环）。
   * action: done / undo / skip / hard / easy / feedback
   * 成功后同步 plan + path —— 完成任务时步骤卡片响应式变绿，无需手动刷新。
   *
   * P3.1 进度回流：done 时把 noteId 加入 userData.readSet（/path 的 ✓ 节点和掌握度同步变绿），
   * undo 时移除。回流只在前端做，不碰后端 feedback（read 由 userData store 独立防抖同步，
   * 避免与后端 save_user_data 竞态）。manual 任务（无 pathStepId）也回流——它仍代表一次真实学习。
   * 用 toggleRead 的切换语义需先判断当前状态，避免误切。
   */
  async function feedback(noteId, action, text = '') {
    try {
      const res = await fetch('/api/agent/study-plan/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ noteId, action, feedback: text }),
      })
      const data = await res.json()
      if (data.ok) {
        plan.value = data.plan
        if (data.path) path.value = data.path
        // P3.1 进度回流：done → 标记已读；undo → 取消已读
        if (noteId && (action === 'done' || action === 'undo')) {
          const ud = useUserDataStore()
          const isRead = ud.readSet.has(noteId)
          if (action === 'done' && !isRead) ud.toggleRead(noteId)
          else if (action === 'undo' && isRead) ud.toggleRead(noteId)
        }
      }
      return data
    } catch (e) {
      return { ok: false, error: e.message }
    }
  }

  /** 手动添加任务（source=manual，完成不推进路径） */
  async function addManualItem(name, noteId = '', estimatedHours = 1) {
    try {
      const res = await fetch('/api/agent/study-plan/item', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, noteId, estimatedHours }),
      })
      const data = await res.json()
      if (data.ok) plan.value = data.plan
      return data
    } catch (e) {
      return { ok: false, error: e.message }
    }
  }

  /**
   * 无路径引导：先调 /agent/recommend-path 生成并落盘路径，成功后自动生成联动计划。
   * @returns {{ok:boolean, error?:string}} 路径生成失败时返回错误（不继续生成计划）
   */
  async function generatePathAndPlan(goal = '') {
    loading.value = true
    error.value = null
    try {
      const r = await agentRecommendPath(goal)
      if (r.error || !r.path?.length) {
        error.value = r.error || '学习路径生成失败'
        return { ok: false, error: error.value }
      }
      if (r.recommendPath) path.value = r.recommendPath
      const g = await generate(goal, '')
      return g
    } catch (e) {
      error.value = e.message
      return { ok: false, error: e.message }
    } finally {
      loading.value = false
    }
  }

  return { plan, path, loading, error, degraded,
           load, loadPath, generate, feedback, addManualItem, generatePathAndPlan }
})
