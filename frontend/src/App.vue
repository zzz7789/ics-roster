<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import RosterGrid from './components/RosterGrid.vue'
import { api } from './api/client.js'
import { daysOfMonth, monthLabel, shiftRange } from './utils/date.js'

const today = new Date()
const year = ref(today.getFullYear())
const month = ref(today.getMonth() + 1)

const persons = ref([])
const shiftTypes = ref([])
const shifts = ref({}) // `${personId}:${iso}` -> shift
const loading = ref(false)
const error = ref('')
const teamToken = ref(localStorage.getItem('ics-roster-team-token') || '')
const newPersonName = ref('')

const days = computed(() => daysOfMonth(year.value, month.value))
const label = computed(() => monthLabel(year.value, month.value))

function keyOf(shift) {
  return `${shift.person_id}:${shift.work_date}`
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const { from, to } = shiftRange(year.value, month.value)
    const [p, t, s] = await Promise.all([
      api.listPersons(),
      api.listShiftTypes(),
      api.listShifts({ from, to }),
    ])
    persons.value = p
    shiftTypes.value = t
    shifts.value = Object.fromEntries(s.map((item) => [keyOf(item), item]))
  } catch (e) {
    error.value = `加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

async function onPick({ personId, iso, shiftTypeId }) {
  const existing = shifts.value[`${personId}:${iso}`]
  try {
    if (shiftTypeId === null) {
      if (existing) {
        await api.deleteShift(existing.id)
        delete shifts.value[`${personId}:${iso}`]
      }
      return
    }
    const saved = await api.saveShift({
      person_id: personId,
      shift_type_id: shiftTypeId,
      work_date: iso,
      note: existing?.note || '',
    })
    shifts.value = { ...shifts.value, [keyOf(saved)]: saved }
  } catch (e) {
    error.value = `保存失败：${e.message}`
  }
}

async function addPerson() {
  const name = newPersonName.value.trim()
  if (!name) return
  try {
    const palette = ['#4f8cff', '#22c55e', '#f5a524', '#ef4444', '#7c5cff', '#06b6d4']
    const person = await api.createPerson({
      name,
      color: palette[persons.value.length % palette.length],
      group_name: '',
    })
    persons.value = [...persons.value, person]
    newPersonName.value = ''
  } catch (e) {
    error.value = `添加失败：${e.message}`
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    error.value = ''
    alert('已复制到剪贴板')
  } catch {
    window.prompt('手动复制下面的地址：', text)
  }
}

function syncToken() {
  localStorage.setItem('ics-roster-team-token', teamToken.value)
}

function saveTeamToken() {
  syncToken()
  alert('已保存，与后端 ICS_ROSTER_TEAM_TOKEN 保持一致即可')
}

watch([year, month], loadAll)
onMounted(loadAll)
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <strong>ics-roster</strong>
        <span class="tagline">排班生成 · 上传 · 可视化 · ICS 订阅</span>
      </div>
      <div class="month-nav">
        <button @click="month === 1 ? ((year -= 1), (month = 12)) : (month -= 1)">‹</button>
        <span class="month-label">{{ label }}</span>
        <button @click="month === 12 ? ((year += 1), (month = 1)) : (month += 1)">›</button>
        <button class="ghost" @click="loadAll">刷新</button>
      </div>
      <div class="feed">
        <input v-model="teamToken" placeholder="团队订阅 token" @change="saveTeamToken" />
        <button class="primary" @click="copyText(api.teamFeedUrl(teamToken))">
          复制团队订阅地址
        </button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="body">
      <aside class="sidebar">
        <h3>人员</h3>
        <form class="add-person" @submit.prevent="addPerson">
          <input v-model="newPersonName" placeholder="姓名" />
          <button class="primary">添加</button>
        </form>
        <ul class="person-list">
          <li v-for="person in persons" :key="person.id">
            <span class="dot" :style="{ background: person.color }"></span>
            <span class="pname">{{ person.name }}</span>
            <button
              class="link"
              title="复制该成员的日历订阅地址"
              @click="copyText(api.personFeedUrl(person))"
            >
              订阅
            </button>
          </li>
          <li v-if="!persons.length" class="empty">暂无人员</li>
        </ul>

        <h3>班次</h3>
        <ul class="type-list">
          <li v-for="type in shiftTypes" :key="type.id">
            <span class="dot" :style="{ background: type.color }"></span>
            {{ type.name }}
            <small v-if="type.start_time">{{ type.start_time }}–{{ type.end_time }}</small>
            <small v-else>不写入日历</small>
          </li>
        </ul>
      </aside>

      <main class="main">
        <RosterGrid
          :persons="persons"
          :days="days"
          :shift-types="shiftTypes"
          :shifts="shifts"
          @pick="onPick"
        />
        <p class="hint">
          点击格子选择班次，选择「清除」删除当天排班。{{ loading ? '加载中…' : '' }}
        </p>
      </main>
    </div>
  </div>
</template>
