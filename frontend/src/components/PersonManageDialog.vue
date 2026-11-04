<script setup>
import { computed, ref } from 'vue'
import { api } from '../api/client.js'

const props = defineProps({
  persons: { type: Array, required: true },
  shifts: { type: Object, required: true },
})
const emit = defineEmits(['close', 'changed'])

const error = ref('')
const busyId = ref(null)

// 统计各成员本月排班条数，删除前给用户看清楚影响
const rows = computed(() =>
  props.persons.map((person) => ({
    ...person,
    monthCount: Object.values(props.shifts).filter((shift) => shift.person_id === person.id)
      .length,
  }))
)

async function copyFeed(person) {
  const url = api.personFeedUrl(person)
  try {
    await navigator.clipboard.writeText(url)
    alert(`已复制「${person.name}」的订阅地址`)
  } catch {
    window.prompt('手动复制下面的地址：', url)
  }
}

async function rotate(person) {
  const ok = window.confirm(
    `轮换「${person.name}」的订阅 token？\n旧订阅地址会立即失效，需要重新订阅。`
  )
  if (!ok) return
  busyId.value = person.id
  error.value = ''
  try {
    await api.rotateToken(person.id)
    emit('changed')
  } catch (e) {
    error.value = `轮换失败：${e.message}`
  } finally {
    busyId.value = null
  }
}

async function remove(person) {
  const extra = person.monthCount
    ? `\n该成员本月已有 ${person.monthCount} 条排班，将一并删除。`
    : ''
  const ok = window.confirm(
    `确定删除「${person.name}」吗？${extra}\n删除后其日历订阅地址立即失效，且不可恢复。`
  )
  if (!ok) return
  busyId.value = person.id
  error.value = ''
  try {
    // purge=true：连同该成员的排班记录一起物理删除
    await api.deletePerson(person.id, true)
    emit('changed')
  } catch (e) {
    error.value = `删除失败：${e.message}`
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal narrow">
      <header class="modal-head">
        <h3>人员管理</h3>
        <button class="icon" @click="emit('close')">×</button>
      </header>

      <div class="modal-body">
        <p v-if="error" class="error inline">{{ error }}</p>
        <p class="muted small">删除会连带清除该成员的全部排班记录，且不可恢复。</p>

        <ul class="member-list">
          <li v-for="person in rows" :key="person.id">
            <span class="dot" :style="{ background: person.color }"></span>
            <span class="pname">{{ person.name }}</span>
            <small class="muted">本月 {{ person.monthCount }} 天</small>
            <div class="member-actions">
              <button class="ghost small-btn" @click="copyFeed(person)">订阅地址</button>
              <button
                class="ghost small-btn"
                :disabled="busyId === person.id"
                title="旧订阅地址立即失效"
                @click="rotate(person)"
              >
                换 token
              </button>
              <button
                class="btn-danger small-btn"
                :disabled="busyId === person.id"
                @click="remove(person)"
              >
                删除
              </button>
            </div>
          </li>
          <li v-if="!rows.length" class="empty">暂无人员</li>
        </ul>
      </div>

      <footer class="modal-foot">
        <button @click="emit('close')">关闭</button>
      </footer>
    </div>
  </div>
</template>
