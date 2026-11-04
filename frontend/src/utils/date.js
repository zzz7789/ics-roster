// 轻量日期工具：全部使用本地时区的 YYYY-MM-DD 字符串，避免 UTC 偏移问题
export function toISODate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function daysOfMonth(year, month) {
  // month: 1-12
  const total = new Date(year, month, 0).getDate()
  const today = toISODate(new Date())
  return Array.from({ length: total }, (_, i) => {
    const date = new Date(year, month - 1, i + 1)
    const iso = toISODate(date)
    return {
      iso,
      day: i + 1,
      weekday: date.getDay(), // 0=周日
      weekend: [0, 6].includes(date.getDay()),
      today: iso === today,
    }
  })
}

export const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六']

export function monthLabel(year, month) {
  return `${year} 年 ${month} 月`
}

export function shiftRange(year, month) {
  const from = toISODate(new Date(year, month - 1, 1))
  const to = toISODate(new Date(year, month, 0))
  return { from, to }
}
