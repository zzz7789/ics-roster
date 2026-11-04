// 开发时走 vite proxy，生产环境与后端同域，默认留空即可
const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    // 会话走 HttpOnly Cookie，同源请求默认携带
    credentials: 'same-origin',
    ...options,
    // FormData 要浏览器自己带 boundary，不能手写 Content-Type
    headers: isForm ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
    } catch {
      detail = await res.text().catch(() => '')
    }
    throw new ApiError(res.status, detail || res.statusText)
  }
  return res.status === 204 ? null : res.json()
}

function uploadFiles(path, files, extra = {}) {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  for (const [key, value] of Object.entries(extra)) form.append(key, value)
  return request(path, { method: 'POST', body: form })
}

export const api = {
  // ---- 登录 ----
  me: () => request('/api/auth/me'),
  login: (username, password) =>
    request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  changePassword: (oldPassword, newPassword) =>
    request('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),

  // ---- 人员 ----
  listPersons: (includeInactive = false) =>
    request(`/api/persons?include_inactive=${includeInactive}`),
  createPerson: (payload) =>
    request('/api/persons', { method: 'POST', body: JSON.stringify(payload) }),
  updatePerson: (id, payload) =>
    request(`/api/persons/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deactivatePerson: (id) => request(`/api/persons/${id}`, { method: 'DELETE' }),
  rotateToken: (id) => request(`/api/persons/${id}/token`, { method: 'POST' }),

  // ---- 班次 / 排班 ----
  listShiftTypes: () => request('/api/shift-types'),
  createShiftType: (payload) =>
    request('/api/shift-types', { method: 'POST', body: JSON.stringify(payload) }),

  listShifts: ({ from, to, personId } = {}) => {
    const params = new URLSearchParams()
    if (from) params.set('from', from)
    if (to) params.set('to', to)
    if (personId) params.set('person_id', personId)
    const qs = params.toString()
    return request(`/api/shifts${qs ? `?${qs}` : ''}`)
  },
  saveShift: (payload) =>
    request('/api/shifts', { method: 'POST', body: JSON.stringify(payload) }),
  bulkSaveShifts: (items) =>
    request('/api/shifts/bulk', { method: 'POST', body: JSON.stringify({ items }) }),
  deleteShift: (id) => request(`/api/shifts/${id}`, { method: 'DELETE' }),

  // ---- ICS 导入 ----
  importPreview: (files) => uploadFiles('/api/import/ics/preview', files),
  importApply: (files, mapping) =>
    uploadFiles('/api/import/ics/apply', files, { mapping: JSON.stringify(mapping) }),

  // ---- Excel 导入 ----
  excelPreview: (files) => uploadFiles('/api/import/excel/preview', files),
  excelApply: (files, options) =>
    uploadFiles('/api/import/excel/apply', files, { options: JSON.stringify(options) }),

  // ---- 订阅地址 ----
  teamFeedUrl: (token) =>
    `${window.location.origin}${BASE}/api/calendar/team.ics?token=${encodeURIComponent(token)}`,
  personFeedUrl: (person) =>
    `${window.location.origin}${BASE}/api/calendar/person/${person.id}/${person.feed_token}.ics`,
}
