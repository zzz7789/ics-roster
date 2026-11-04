<script setup>
import { ref } from 'vue'
import IcsImport from './IcsImport.vue'
import ExcelImport from './ExcelImport.vue'

defineProps({
  persons: { type: Array, required: true },
  shiftTypes: { type: Array, required: true },
})
const emit = defineEmits(['close', 'imported'])

// 默认走 Excel：日常排班表多为月度 xlsx
const tab = ref('excel')
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
          <button class="tab" :class="{ active: tab === 'excel' }" @click="switchTab('excel')">
            导入 Excel
          </button>
          <button class="tab" :class="{ active: tab === 'ics' }" @click="switchTab('ics')">
            导入 ICS
          </button>
        </div>
        <button class="icon" @click="emit('close')">×</button>
      </header>

      <ExcelImport
        v-if="tab === 'excel'"
        :key="`excel-${activeKey}`"
        :persons="persons"
        :shift-types="shiftTypes"
        @close="emit('close')"
        @imported="emit('imported')"
      />
      <IcsImport
        v-else
        :key="`ics-${activeKey}`"
        :persons="persons"
        :shift-types="shiftTypes"
        @close="emit('close')"
        @imported="emit('imported')"
      />
    </div>
  </div>
</template>
