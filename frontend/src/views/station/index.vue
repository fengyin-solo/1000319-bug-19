<template>
  <section class="page" data-module="station">
    <header class="page-head">
      <div>
        <h2>光伏电站管理</h2>
        <p class="page-desc">维护电站档案，围绕电站编码、电站名称、装机容量、并网电压等级做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记电站档案</button>
        <button class="btn" type="button" :disabled="loading" @click="exportRows">导出光伏电站清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applySearch">
      <label class="filter-item">
        <span>电站编码</span>
        <input v-model="draft.keyword" placeholder="按电站编码检索" />
      </label>
      <label class="filter-item">
        <span>所属区域</span>
        <input v-model="draft.region" placeholder="按所属区域检索" />
      </label>
      <label class="filter-item">
        <span>电站状态</span>
        <select v-model="draft.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit" :disabled="loading">查询</button>
      <button class="btn ghost" type="button" :disabled="loading" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ cellText(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条光伏电站记录，第 {{ page }} / {{ totalPages }} 页</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="turnPage(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="page >= totalPages || loading" @click="turnPage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type Conditions = { keyword: string; region: string; status: string }

const ENDPOINT = '/api/station'
const PAGE_SIZE = 10
const columns = ["电站编码", "电站名称", "装机容量", "并网电压等级", "所属区域", "投运日期", "运维班组", "电站状态"]
const actions = ["办理并网", "申请限电", "停运电站"]
const statuses = ["在建", "已投运", "限电中", "已停运"]
const stats = [{"label": "在运电站", "value": 0}, {"label": "限电电站", "value": 0}, {"label": "本月新增并网", "value": 0}]

const route = useRoute()
const router = useRouter()

// 表单里的草稿条件：点「查询」后才会落到 applied，翻页与导出只认 applied
const draft = ref<Conditions>({ keyword: '', region: '', status: '' })
const applied = ref<Conditions>({ keyword: '', region: '', status: '' })

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasActiveFilters = computed(() =>
  Boolean(applied.value.keyword || applied.value.region || applied.value.status),
)
const activeFilterText = computed(() => {
  const parts: string[] = []
  if (applied.value.keyword) parts.push(`电站编码包含「${applied.value.keyword}」`)
  if (applied.value.region) parts.push(`所属区域包含「${applied.value.region}」`)
  if (applied.value.status) parts.push(`电站状态为「${applied.value.status}」`)
  return parts.join('、')
})
const emptyText = computed(() => {
  if (errorMessage.value) return '列表加载失败，请根据右侧提示检查条件后重试'
  if (hasActiveFilters.value) {
    return `当前条件（${activeFilterText.value}）没有命中任何电站，请调整条件后重新查询，或点「重置条件」回到全量`
  }
  return '暂无光伏电站数据，可先登记电站档案'
})

function cellText(row: Row, column: string): string | number | boolean | null {
  // 电站状态以状态流转写入的 status 为准，保证列表、筛选与导出口径一致
  const value = column === '电站状态' ? (row.status ?? row[column]) : row[column]
  return value === null || value === undefined || value === '' ? '—' : value
}

function conditionParams(): URLSearchParams {
  // 列表、分页、导出共用这一套查询条件，只在这里拼一次
  const params = new URLSearchParams()
  if (applied.value.keyword) params.set('keyword', applied.value.keyword)
  if (applied.value.region) params.set('region', applied.value.region)
  if (applied.value.status) params.set('status', applied.value.status)
  return params
}

function trimmedDraft(): Conditions {
  return {
    keyword: draft.value.keyword.trim(),
    region: draft.value.region.trim(),
    status: draft.value.status,
  }
}

async function syncRouteQuery() {
  // 条件与页码写进地址栏：翻页、跳到别的页面再返回、刷新都不会丢
  const query: Record<string, string> = {}
  if (applied.value.keyword) query.keyword = applied.value.keyword
  if (applied.value.region) query.region = applied.value.region
  if (applied.value.status) query.status = applied.value.status
  if (page.value > 1) query.page = String(page.value)
  await router.replace({ query })
}

async function applySearch() {
  applied.value = trimmedDraft()
  page.value = 1
  await syncRouteQuery()
  await reload()
}

async function turnPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value || loading.value) return
  page.value = target
  await syncRouteQuery()
  await reload()
}

async function resetFilters() {
  draft.value = { keyword: '', region: '', status: '' }
  applied.value = { keyword: '', region: '', status: '' }
  page.value = 1
  await router.replace({ query: {} })
  await reload()
}

async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string' && data.detail) return data.detail
  } catch {
    // 返回的不是 JSON（例如网关错误页），退回通用提示
  }
  return fallback
}

async function exportRows() {
  errorMessage.value = ''
  loading.value = true
  try {
    // 导出与列表走同一套条件；命中为空时后端会返回原因，不产出空文件
    const response = await request(`${ENDPOINT}/export?${conditionParams().toString()}`)
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, '光伏电站清单导出失败，请稍后重试'))
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '光伏电站清单.csv'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '光伏电站清单导出失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  errorMessage.value = '电站档案登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('光伏电站动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '光伏电站操作失败'
  }
}

async function reload() {
  loading.value = true
  errorMessage.value = ''
  const params = conditionParams()
  params.set('page', String(page.value))
  params.set('size', String(PAGE_SIZE))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error(await readErrorDetail(response, '电站档案列表读取失败'))
    }
    const payload = await response.json()
    const items: Row[] = payload.items ?? []
    const payloadTotal: number = payload.total ?? 0
    // 页码超出范围（比如地址栏里的旧页码）时回到最后一页，不拿空页冒充无数据
    if (!items.length && payloadTotal > 0 && page.value > 1) {
      page.value = Math.max(1, Math.ceil(payloadTotal / PAGE_SIZE))
      await syncRouteQuery()
      await reload()
      return
    }
    rows.value = items
    total.value = payloadTotal
    page.value = payload.page ?? page.value
  } catch (error) {
    rows.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '光伏电站列表读取失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 从地址栏恢复上次的条件与页码，返回页面时不回到全量
  const query = route.query
  const status = typeof query.status === 'string' && statuses.includes(query.status) ? query.status : ''
  applied.value = {
    keyword: typeof query.keyword === 'string' ? query.keyword : '',
    region: typeof query.region === 'string' ? query.region : '',
    status,
  }
  draft.value = { ...applied.value }
  const queryPage = Number(query.page)
  page.value = Number.isInteger(queryPage) && queryPage >= 1 ? queryPage : 1
  void reload()
})
</script>
