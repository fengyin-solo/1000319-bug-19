<template>
  <section class="page" data-module="station">
    <header class="page-head">
      <div>
        <h2>光伏电站管理</h2>
        <p class="page-desc">维护电站档案，围绕电站编码、电站名称、装机容量、并网电压等级做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记电站档案</button>
        <button class="btn" type="button" @click="exportRows">导出光伏电站清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
        <tr v-if="!loading && !rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条光伏电站记录</span>
      <div v-if="totalPages > 1" class="pager">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button
          class="btn"
          type="button"
          :disabled="page >= totalPages || loading"
          @click="goPage(page + 1)"
        >
          下一页
        </button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FilterKey = 'code' | 'region'

const ENDPOINT = '/api/station'
const columns = ["电站编码", "电站名称", "装机容量", "并网电压等级", "所属区域", "投运日期", "运维班组", "电站状态"]
const actions = ["办理并网", "申请限电", "停运电站"]
const statuses = ["在建", "已投运", "限电中", "已停运"]
const stats = [{"label": "在运电站", "value": 0}, {"label": "限电电站", "value": 0}, {"label": "本月新增并网", "value": 0}]
const PAGE_SIZE = 20

// 查询条件与后端参数一一对应；keyword 只是 code 的旧参数名，这里统一发 code
const filterFields: Array<{ key: FilterKey; label: string }> = [
  { key: 'code', label: '电站编码' },
  { key: 'region', label: '所属区域' },
]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')
const filters = reactive<Record<FilterKey, string>>({ code: '', region: '' })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const activeFilters = computed(() =>
  (Object.keys(filters) as FilterKey[]).filter((key) => filters[key].trim() !== '')
)
const emptyText = computed(() =>
  activeFilters.value.length
    ? '当前筛选条件下没有命中的电站，请调整条件后重新查询，或点“重置条件”查看全部电站'
    : '暂无光伏电站数据，可先登记电站档案'
)

// 列表、分页、导出共用这一份查询参数，保证三者口径一致
function buildQuery(targetPage: number): Record<string, string> {
  const query: Record<string, string> = {}
  for (const key of Object.keys(filters) as FilterKey[]) {
    const value = filters[key].trim()
    if (value) {
      query[key] = value
    }
  }
  if (targetPage > 1) {
    query.page = String(targetPage)
  }
  return query
}

function syncFromRoute() {
  filters.code = typeof route.query.code === 'string' ? route.query.code : ''
  filters.region = typeof route.query.region === 'string' ? route.query.region : ''
  const routePage = Number(route.query.page)
  page.value = Number.isInteger(routePage) && routePage >= 1 ? routePage : 1
}

function search() {
  errorMessage.value = ''
  // 条件不完整时先说明原因，不发请求，避免空列表让人误以为没有电站
  if (!activeFilters.value.length) {
    errorMessage.value = '请先填写电站编码或所属区域等查询条件；如需查看全部电站，请点“重置条件”'
    return
  }
  void router.push({ query: buildQuery(1) })
}

function resetFilters() {
  errorMessage.value = ''
  void router.push({ query: {} })
}

function goPage(target: number) {
  if (target < 1 || target > totalPages.value) {
    return
  }
  errorMessage.value = ''
  void router.push({ query: buildQuery(target) })
}

async function exportRows() {
  errorMessage.value = ''
  // 导出与当前列表同一套条件：带条件时导出命中项，重置后的全量视图则导出全量
  if (activeFilters.value.length && total.value === 0) {
    errorMessage.value = '当前筛选条件下没有可导出的电站，请调整条件后重新查询，或点“重置条件”导出全部电站'
    return
  }
  const params: Record<string, string> = {}
  for (const key of Object.keys(filters) as FilterKey[]) {
    const value = filters[key].trim()
    if (value) {
      params[key] = value
    }
  }
  const query = new URLSearchParams(params).toString()
  try {
    const response = await request(`${ENDPOINT}/export?${query}`)
    if (!response.ok) {
      let message = '导出失败，请稍后重试'
      try {
        const payload = (await response.json()) as { detail?: string }
        if (payload.detail) {
          message = payload.detail
        }
      } catch {
        // 后端没给可读原因时保留默认提示
      }
      throw new Error(message)
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '光伏电站清单.csv'
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '光伏电站清单导出失败'
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
  try {
    const query = new URLSearchParams(buildQuery(page.value)).toString()
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      let message = '电站档案列表读取失败'
      try {
        const payload = (await response.json()) as { detail?: string }
        if (payload.detail) {
          message = payload.detail
        }
      } catch {
        // 沿用默认提示
      }
      throw new Error(message)
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '光伏电站列表读取失败'
  } finally {
    loading.value = false
  }
}

// 条件与页码都落在 URL 上：翻页、浏览器前进/后退、从别的页面返回时自动恢复，不会被清空
watch(
  () => route.query,
  () => {
    syncFromRoute()
    void reload()
  },
  { immediate: true }
)
</script>
