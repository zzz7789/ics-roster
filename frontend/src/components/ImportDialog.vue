<script setup>
import { ref } from 'vue'
import IcsImport from './IcsImport.vue'
import ExcelImport from './ExcelImport.vue'

defineProps({
  persons: { type: Array, required: true },
  shiftTypes: { type: Array, required: true },
})
const emit = defineEmits(['close', 'imported'])

const tab = ref('ics')
const activeKey = ref(0)

// 切换 tab 时重建子组件，避免残留上一次的状态
function switchTab(next) {
  if (tab.value === next) return
  tab.value = next
  activeKey.value += 1
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <header class="modal-head">
        <div class="tabs">
          <button class="tab" :class="{ active: tab === 'ics' }" @click="switchTab('ics')">
            导入 ICS
          </button>
          <button class="tab" :class="{ active: tab === 'excel' }" @click="switchTab('excel')">
            导入 Excel
          </button>
        </div>
        <button class="icon" @click="emit('close')">×</button>
      </header>

      <IcsImport
        v-if="tab === 'ics'"
        :key="`ics-${activeKey}`"
        :persons="persons"
        :shift-types="shiftTypes"
        @close="emit('close')"
        @imported="emit('imported')"
      />
      <ExcelImport
        v-else
        :key="`excel-${activeKey}`"
        :persons="persons"
        :shift-types="shiftTypes"
        @close="emit('close')"
        @imported="emit('imported')"
      />
    </div>
  </div>
</template>
