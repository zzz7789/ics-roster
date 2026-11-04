<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api/client.js'

const props = defineProps({
  persons: { type: Array, required: true },
  shiftTypes: { type: Array, required: true },
})
const emit = defineEmits(['close', 'imported'])

const step = ref('pick') // pick -> map -> done
const files = ref([])
const preview = ref(null)
const rows = ref({})
const busy = ref(false)
const error = ref('')
const result = ref(null)

const bulkPerson = ref('')
const bulkNewName = ref('')

const unmapped = computed(
  () =>
    Object.values(rows.value).filter(
      (row) => !row.selected || row.personId === 'ignore' || !row.shiftTypeId,
    ).length,
)

const selectedRows = computed(() => Object.values(rows.value).filter((row) => row.selected))
const allSelected = computed(
  () => selectedRows.value.length === Object.values(rows.value).length && selectedRows.value.length > 0,
)
const someSelected = computed(() => selectedRows.value.length > 0 && !allSelected.value)

// 未勾选时会带来“这次不导入”的影响，提示预留：选中组覆盖的事件数
const selectedEvents = computed(() => {
  if (!preview.value) return 0
  return preview.value.groups
    .filter((group) => rows.value[group.key]?.selected)
    .reduce((sum, group) => sum + group.count, 0)
})

const headBox = ref(null)
watch([allSelected, someSelected], () => {
  if (headBox.value) headBox.value.indeterminate = !allSelected.value && someSelected.value
})

function toggleAll(next) {
  for (const row of Object.values(rows.value)) row.selected = next
}

function pickFiles(event) {
  files.value = Array.from(event.target.files || [])
}

function applyBulkPerson() {
  if (!bulkPerson.value) return
  for (const row of Object.values(rows.value)) {
    row.personId = bulkPerson.value
    if (bulkPerson.value === 'new') row.newName = bulkNewName.value
  }
}

async function doPreview() {
  if (!files.value.length) {
    error.value = '请先选择 .ics 文件'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const data = await api.importPreview(files.value)
    preview.value = data
    const next = {}
    for (const group of data.groups) {
      next[group.key] = {
        key: group.key,
        selected: true,
        personId: group.suggested_person_id ?? 'new',
        newName: group.suggested_new_person_name || '',
        shiftTypeId: group.suggested_shift_type_id ?? (props.shiftTypes[0]?.id ?? null),
      }
    }
    rows.value = next
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
    const mapping = {}
    for (const row of Object.values(rows.value)) {
      // 取消勾选的分组明确告知后端跳过，避免计入「未指定映射」告警
      if (!row.selected || row.personId === 'ignore') {
        mapping[row.key] = { skip: true }
        continue
      }
      if (row.personId === 'new') {
        if (!row.newName.trim()) throw new Error('有分组选择了「新建人员」但没有填姓名')
        mapping[row.key] = {
          new_person_name: row.newName.trim(),
          shift_type_id: row.shiftTypeId,
        }
      } else {
        mapping[row.key] = { person_id: row.personId, shift_type_id: row.shiftTypeId }
      }
    }
    result.value = await api.importApply(files.value, mapping)
    step.value = 'done'
    emit('imported')
  } catch (e) {
    error.value = `导入失败：${e.message}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div>
    <p v-if="error" class="error inline">{{ error }}</p>

    <section v-if="step === 'pick'" class="modal-body">
      <p class="muted">
        选择已有的 <code>.ics</code> 排班文件（可多选）。系统会解析出事件，按「标题 + 时段」分组，
        再让你确认每条分组对应哪位人员、哪个班次。
      </p>
      <input type="file" accept=".ics,text/calendar" multiple @change="pickFiles" />
      <ul class="file-list">
        <li v-for="file in files" :key="file.name">
          {{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）
        </li>
      </ul>
      <p class="hint-box">支持：定时事件 / 全天事件 / 跨天班次 / 重复规则（每天·每周·每月）。</p>
    </section>

    <section v-else-if="step === 'map'" class="modal-body">
      <p class="muted small">
        共 {{ preview.total_events }} 条事件，分为 {{ preview.groups.length }} 组。
        只有勾选的分组会写入（已选 {{ selectedRows.length }} 组 / {{ selectedEvents }} 条事件）。
      </p>

      <div class="bulk-bar">
        <span class="muted small">批量设置人员</span>
        <select v-model="bulkPerson">
          <option value="">选择人员…</option>
          <option v-for="person in persons" :key="person.id" :value="person.id">
            {{ person.name }}
          </option>
          <option value="new">＋ 新建人员</option>
        </select>
        <input v-if="bulkPerson === 'new'" v-model="bulkNewName" placeholder="新人员姓名" />
        <button class="ghost" :disabled="!bulkPerson" @click="applyBulkPerson">应用到全部</button>
        <span class="muted small">整份文件属于同一个人时用</span>
      </div>

      <div class="table-scroll">
        <table class="map-table">
          <thead>
            <tr>
              <th class="pick-col">
                <input
                  ref="headBox"
                  type="checkbox"
                  :checked="allSelected"
                  title="全选 / 全不选"
                  @change="toggleAll($event.target.checked)"
                />
              </th>
              <th>原始标题</th>
              <th>时段</th>
              <th>次数</th>
              <th>日期范围</th>
              <th>人员</th>
              <th>班次</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="group in preview.groups"
              :key="group.key"
              :class="{ 'row-off': !rows[group.key].selected }"
            >
              <td class="pick-col">
                <input v-model="rows[group.key].selected" type="checkbox" />
              </td>
              <td class="title" :title="group.summary">{{ group.summary }}</td>
              <td class="nowrap">{{ group.time_label }}</td>
              <td class="num">{{ group.count }}</td>
              <td class="nowrap small">
                {{ group.first_date
                }}<span v-if="group.last_date !== group.first_date"> ~ {{ group.last_date }}</span>
              </td>
              <td>
                <select v-model="rows[group.key].personId">
                  <option value="ignore">忽略此行</option>
                  <option v-for="person in persons" :key="person.id" :value="person.id">
                    {{ person.name }}
                  </option>
                  <option value="new">＋ 新建人员</option>
                </select>
                <input
                  v-if="rows[group.key].personId === 'new'"
                  v-model="rows[group.key].newName"
                  class="new-name"
                  placeholder="新人员姓名"
                />
              </td>
              <td>
                <select v-model="rows[group.key].shiftTypeId">
                  <option v-for="type in shiftTypes" :key="type.id" :value="type.id">
                    {{ type.name }}
                  </option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul v-if="preview.warnings.length" class="warn-list">
        <li v-for="(warn, idx) in preview.warnings" :key="idx">{{ warn }}</li>
      </ul>
    </section>

    <section v-else class="modal-body">
      <p class="ok">
        导入完成：新增 {{ result.created }} 条，更新 {{ result.updated }} 条，跳过
        {{ result.skipped }} 条。
      </p>
      <ul v-if="result.warnings.length" class="warn-list">
        <li v-for="(warn, idx) in result.warnings" :key="idx">{{ warn }}</li>
      </ul>
    </section>

    <footer class="modal-foot">
      <span v-if="step === 'map'" class="muted small">
        已选 {{ selectedRows.length }} / {{ preview.groups.length }} 组
        <template v-if="unmapped">，其中 {{ unmapped }} 组不会写入</template>
      </span>
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
