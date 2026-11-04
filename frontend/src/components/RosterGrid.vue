<script setup>
import { computed, ref } from 'vue'
import { WEEKDAY_LABELS } from '../utils/date.js'

const props = defineProps({
  persons: { type: Array, required: true },
  days: { type: Array, required: true },
  shiftTypes: { type: Array, required: true },
  shifts: { type: Object, required: true }, // key: `${personId}:${iso}`
})

const emit = defineEmits(['pick'])

const picking = ref(null) // { personId, iso, x, y }

const typeById = computed(() => Object.fromEntries(props.shiftTypes.map((t) => [t.id, t])))

function cell(person, day) {
  return props.shifts[`${person.id}:${day.iso}`]
}

function typeOf(shift) {
  return typeById.value[shift?.shift_type_id]
}

function chipStyle(shift) {
  const color = typeOf(shift)?.color || '#94a3b8'
  return { background: `${color}22`, color }
}

function nameOf(shift) {
  return typeOf(shift)?.name || '未定义'
}

function openPicker(event, person, day) {
  const rect = event.currentTarget.getBoundingClientRect()
  picking.value = {
    personId: person.id,
    iso: day.iso,
    name: person.name,
    x: rect.left + window.scrollX,
    y: rect.bottom + window.scrollY + 4,
  }
}

function choose(shiftTypeId) {
  const { personId, iso } = picking.value
  emit('pick', { personId, iso, shiftTypeId })
  picking.value = null
}
</script>

<template>
  <div class="grid-wrap">
    <table class="roster">
      <thead>
        <tr>
          <th class="person-col">人员</th>
          <th v-for="day in days" :key="day.iso" :class="{ weekend: day.weekend, today: day.today }">
            <span class="day-num">{{ day.day }}</span>
            <span class="day-dow">{{ WEEKDAY_LABELS[day.weekday] }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="person in persons" :key="person.id">
          <th class="person-col">
            <span class="dot" :style="{ background: person.color }"></span>
            <span class="pname">{{ person.name }}</span>
            <span v-if="person.group_name" class="pgroup">{{ person.group_name }}</span>
          </th>
          <td
            v-for="day in days"
            :key="day.iso"
            :class="{
              weekend: day.weekend,
              today: day.today,
              filled: !!cell(person, day),
            }"
            @click="openPicker($event, person, day)"
          >
            <span
              v-if="cell(person, day)"
              class="chip"
              :style="chipStyle(cell(person, day))"
            >
              {{ nameOf(cell(person, day)) }}
            </span>
          </td>
        </tr>
        <tr v-if="!persons.length">
          <td :colspan="days.length + 1" class="empty">还没有人员，先在左侧添加</td>
        </tr>
      </tbody>
    </table>

    <!-- Teleport 到 body：iOS 上 .grid-wrap 有横向滚动层叠上下文，
         fixed 定位的选择器留在里面会被定位到表格内，表现为“点了没反应” -->
    <Teleport to="body">
      <div v-if="picking" class="picker-mask" @click="picking = null"></div>
      <div
        v-if="picking"
        class="picker"
        :style="{ left: `${picking.x}px`, top: `${picking.y}px` }"
        @click.stop
      >
        <div class="picker-title">{{ picking.name }} · {{ picking.iso }}</div>
        <button
          v-for="type in shiftTypes"
          :key="type.id"
          class="picker-item"
          @click="choose(type.id)"
        >
          <span class="dot" :style="{ background: type.color }"></span>
          {{ type.name }}
          <small v-if="type.start_time">{{ type.start_time }}–{{ type.end_time }}</small>
        </button>
        <button class="picker-item clear" @click="choose(null)">清除</button>
      </div>
    </Teleport>
  </div>
</template>
