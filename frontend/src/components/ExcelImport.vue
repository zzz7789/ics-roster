<script setup>
import { computed, ref } from 'vue'
import { api } from '../api/client.js'

const props = defineProps({
  persons: { type: Array, required: true },
  shiftTypes: { type: Array, required: true },
})
const emit = defineEmits(['imported'])

const step = ref('pick')
const files = ref([])
const preview = ref(null)
const shiftMap = ref({})
const year = ref(0)
const month = ref(1)
const busy = ref(false)
const error = ref('')
const result = ref(null)

const firstSheet = computed(() => preview.value?.sheets?.[0] || null)
const labels = computed(() => {
  const set = new Set()
  for (const sheet of preview.value?.sheets || []) {
    for (const label of sheet.shift_labels) set.add(label)
  }
  return [...set]
})
const totalDays = computed(() =>
  (preview.value?.sheets || []).reduce(
    (sum, sheet) => sum + sheet.people.reduce((acc, p) => acc + p.day_count, 0),
    0,
  ),
)

function pickFiles(event) {
  files.value = Array.from(event.target.files || [])
}

async function doPreview() {
  if (!files.value.length) {
    error.value = '请先选择 .xlsx 文件'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const data = await api.excelPreview(files.value)
    preview.value = data
    const merged = {}
    for (const sheet of data.sheets) {
      for (const label of sheet.shift_labels) {
        if (!(label in merged)) merged[label] = sheet.label_suggestions?.[label] ?? null
      }
    }
    shiftMap.value = merged
    year.value = data.sheets[0].year
    month.value = data.sheets[0].month
    step.value = 'map'
  } catch (e) {
    error.value = `解析失败：${e.message}`
  } finally {
    busy.value = false
  }
}

async function doApply() {
  busy.value = true
  error.value = ''
  try {
    const options = {
      shift_map: Object.fromEntries(
        Object.entries(shiftMap.value).filter(([, typeId]) => !!typeId),
      ),
      person_map: {},
      year: Number(year.value),
      month: Number(month.value),
    }
    result.value = await api.excelApply(files.value, options)
    step.value = 'done'
    emit('imported')
  } catch (e) {
    error.value = `导入失败：${e.message}`
  } finally {
    busy.value = false
  }
}

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
</script>

<template>
  <div>
    <p v-if="error" class="error inline">{{ error }}</p>

    <section v-if="step === 'pick'" class="modal-body">
      <p class="muted">
        选择月度排班表 <code>.xlsx</code>（一人一行、一天一列）。系统会自动识别表头、日期列与人员行，
        并用「日号 + 星期」反推年月，不需要手动填日期。
      </p>
      <input type="file" accept=".xlsx,.xlsm" multiple @change="pickFiles" />
      <ul class="file-list">
        <li v-for="file in files" :key="file.name">
          {{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）
        </li>
      </ul>
      <p class="hint-box">
        要求：表头行包含「姓名」列，上一行为日号，表头为周一到周日；支持表尾统计行、备注区、
        名称写成「早/晚/休」这类简称。旧版 <code>.xls</code> 请先另存为 <code>.xlsx</code>。
      </p>
    </section>

    <section v-else-if="step === 'map'" class="modal-body">
      <div class="info-row">
        <span>{{ firstSheet.filename }} · {{ firstSheet.sheet_name }}</span>
        <span>
          年月：
          <input v-model.number="year" class="year-input" type="number" min="2000" max="2100" />
          年
          <select v-model.number="month">
            <option v-for="m in MONTHS" :key="m" :value="m">{{ m }}</option>
          </select>
          月
          <span v-if="firstSheet.date_matched" class="badge ok">自动识别</span>
          <span v-else class="badge warn">请核对</span>
        </span>
        <span>人员 <b>{{ firstSheet.people.length }}</b> 人</span>
        <span>共 <b>{{ totalDays }}</b> 个班次</span>
      </div>

      <div class="map-block">
        <h4>班次对应关系</h4>
        <div class="label-row">
          <div v-for="label in labels" :key="label" class="label-item">
            <span class="label-chip">{{ label }}</span>
            <span class="arrow">→</span>
            <select v-model="shiftMap[label]">
              <option :value="null">不导入</option>
              <option v-for="type in shiftTypes" :key="type.id" :value="type.id">
                {{ type.name }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <div class="map-block">
        <h4>人员（同名自动复用，不存在则新建）</h4>
        <div class="people-scroll">
          <table class="map-table">
            <thead>
              <tr>
                <th>姓名</th>
                <th>状态</th>
                <th>天数</th>
                <th>班次分布</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="person in firstSheet.people" :key="person.name">
                <td class="nowrap">{{ person.name }}</td>
                <td class="nowrap">
                  <span v-if="person.person_id" class="badge ok">已有</span>
                  <span v-else class="badge">新建</span>
                </td>
                <td class="num">{{ person.day_count }}</td>
                <td class="nowrap small muted">
                  {{ Object.entries(person.counts).map(([k, v]) => `${k} ${v}`).join(' · ') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <ul v-if="preview.warnings.length" class="warn-list">
        <li v-for="(warn, idx) in preview.warnings" :key="idx">{{ warn }}</li>
      </ul>
    </section>

    <section v-else class="modal-body">
      <p class="ok">
        导入完成：新增 {{ result.created }} 条，更新 {{ result.updated }} 条，跳过 {{ result.skipped }} 条，
        新建人员 {{ result.persons_created }} 人。
      </p>
      <ul v-if="result.warnings.length" class="warn-list">
        <li v-for="(warn, idx) in result.warnings" :key="idx">{{ warn }}</li>
      </ul>
    </section>

    <footer class="modal-foot">
      <button class="ghost" @click="emit('close')">{{ step === 'done' ? '关闭' : '取消' }}</button>
      <button v-if="step === 'pick'" class="primary" :disabled="busy" @click="doPreview">
        {{ busy ? '解析中…' : '解析预览' }}
      </button>
      <button v-if="step === 'map'" class="primary" :disabled="busy" @click="doApply">
        {{ busy ? '导入中…' : '确认导入' }}
      </button>
    </footer>
  </div>
</template>
