// 开发时走 vite proxy，生产环境与后端同域，默认留空即可
const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request(path, options = {}) {
  const isForm = options.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
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
    throw new Error(`${res.status} ${detail || res.statusText}`)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  listPersons: (includeInactive = false) =>
    request(`/api/persons?include_inactive=${includeInactive}`),  createPerson: (payload) =>
    request('/api/persons', { method: 'POST', body: JSON.stringify(payload) }),
  updatePerson: (id, payload) =>
    request(`/api/persons/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deactivatePerson: (id) => request(`/api/persons/${id}`, { method: 'DELETE' }),
  rotateToken: (id) => request(`/api/persons/${id}/token`, { method: 'POST' }),

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

  importPreview: (files) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request('/api/import/ics/preview', { method: 'POST', body: form })
  },
  importApply: (files, mapping) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    form.append('mapping', JSON.stringify(mapping))
    return request('/api/import/ics/apply', { method: 'POST', body: form })
  },

  // 供「复制订阅地址」按钮使用
  teamFeedUrl: (token) =>
    `${window.location.origin}${BASE}/api/calendar/team.ics?token=${encodeURIComponent(token)}`,
  personFeedUrl: (person) =>
    `${window.location.origin}${BASE}/api/calendar/person/${person.id}/${person.feed_token}.ics`,
}
