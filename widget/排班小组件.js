// ==== 一般不用改这里 ====
// 组件会自己在系统「日历」里找名字带「排班」的订阅日历：
//   - 只订阅了一份（单人使用最常见）：直接用它，零配置
//   - 订阅了多份：长按组件 →「编辑小组件」→ Parameter 填自己的名字（如「张三」），
//     也可以填完整日历名（如「张三 排班」）
// 脚本版本（排查界面会显示，用来确认手机上装的是哪一版）
const WIDGET_VERSION = "v6"

// 下面两项是脚本内兜底值，留空即可。
const CALENDAR_TITLE = "" // 固定日历名，留空 = 自动查找
const PERSON_NAME = "" // 团队日历里自己的名字，留空 = 用组件参数

// 事件标题关键字 → 班次代码，命中即可（兼容「早班」和「张三 早班」两种写法）
const SHIFT_KEYWORDS = [
  { code: "早", words: ["早班"] },
  { code: "晚", words: ["晚班"] },
  { code: "休", words: ["休息"] },
]
let calendarEvents = []
let calendarIssue = null
let calendarTitle = "" // 实际选中的日历名，用来判断是不是团队日历
let calendarNames = [] // 系统里能看到的日历名，读写失败时用于排查
let calendarError = "" // 读取日历时的异常信息
let calendarApi = "" // 成功枚举日历用到的 Scriptable API 名
const widgetParameter =
  typeof args !== "undefined" && args && args.widgetParameter
    ? String(args.widgetParameter).trim()
    : ""
const nameHint = widgetParameter || PERSON_NAME // 团队日历里自己的名字
const titleHint = widgetParameter || CALENDAR_TITLE // 用来挑选日历

const COLOR = {
  background: "F2F2F7",
  card: "FFFFFF",
  todayFill: "EAF3FF",
  text: "1C1C1E",
  muted: "6D6D72",
  faint: "8E8E93",
  today: "0A84FF",
}

const SHIFT = {
  // 使用 iOS 系统色：绿色早班、橙色晚班、青色休息。
  // 起止时间不写死，统一从日历事件的 DTSTART/DTEND 读取（见 timeText）。
  "早": { name: "早班", label: "早", hex: "30D158", color: new Color("30D158") },
  "晚": { name: "晚班", label: "晚", hex: "FF9F0A", color: new Color("FF9F0A") },
  "休": { name: "休息", label: "休", hex: "5AC8FA", color: new Color("5AC8FA") },
  "冲": { name: "排班冲突", label: "冲", hex: "FF453A", color: new Color("FF453A") },
}

function atMidnight(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function dateSerial(date) {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000
}

function daysBetween(left, right) {
  return dateSerial(left) - dateSerial(right)
}

function codeOfEvent(item) {
  const title = String(item.title || "").trim()
  // 单人日历的事件标题就是「早班」；团队日历才是「张三 早班」，需要按姓名过滤
  if (calendarTitle.includes("团队") && nameHint && !title.includes(nameHint)) return null
  for (const entry of SHIFT_KEYWORDS) {
    if (entry.words.some(word => title.includes(word))) return entry.code
  }
  return null
}

// 时间来自事件本身：休息是全天事件，晚班会跨到次日 00:00
function timeText(item) {
  if (item.isAllDay) return "全天休息"
  const format = value => `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`
  const crossDay = dateSerial(item.endDate) !== dateSerial(item.startDate)
  return `${format(item.startDate)} – ${crossDay ? "次日 " : ""}${format(item.endDate)}`
}

function shiftFor(date) {
  const matches = []
  for (const item of calendarEvents) {
    const code = codeOfEvent(item)
    if (!code) continue
    if (daysBetween(item.startDate, date) === 0) {
      matches.push({ code, item })
      continue
    }

    // 全天的跨日事件结束时间是排他的；例如 1 日至 3 日表示覆盖 1、2 日。
    const coversDate = item.isAllDay
      && dateSerial(date) >= dateSerial(item.startDate)
      && dateSerial(date) < dateSerial(item.endDate)
    if (coversDate) matches.push({ code, item })
  }

  const codes = [...new Set(matches.map(match => match.code))]
  if (codes.length > 1) return { ...SHIFT["冲"], time: "请检查当天日历" }
  if (codes.length === 0) return null
  return { ...SHIFT[matches[0].code], time: timeText(matches[0].item) }
}

// 统计某个月各班次的天数，用于底部图例
function monthCounts(year, month) {
  const counts = { "早": 0, "晚": 0, "休": 0 }
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  for (let day = 1; day <= daysInMonth; day++) {
    const shift = shiftFor(new Date(year, month, day))
    if (shift && counts[shift.label] !== undefined) counts[shift.label] += 1
  }
  return counts
}

// 按标题找日历：Scriptable 找不到时会抛异常（而不是返回 null），这里统一吞掉
async function findCalendarByTitle(title) {
  if (!title) return null
  try {
    return (await Calendar.forEventsByTitle(title)) || null
  } catch (error) {
    return null
  }
}

// 用户可能只填了姓名（如「张三」），自动补上 ics-roster 的「XXX 排班」命名
async function findCalendarByHint(hint) {
  if (!hint) return null
  const candidates = [hint, `${hint} 排班`, `${hint}排班`]
  for (const title of candidates) {
    const calendar = await findCalendarByTitle(title)
    if (calendar) return calendar
  }
  return null
}

// 枚举事件日历：Scriptable 不同版本可用 API 不同，逐个尝试
// （旧版没有 Calendar.getAllCalendars，只有 Calendar.forEvents）
function listEventCalendars() {
  for (const api of ["forEvents", "getAllCalendars"]) {
    const method = Calendar[api]
    if (typeof method !== "function") continue
    try {
      const list = method.call(Calendar)
      if (list && list.length) return { list: Array.from(list), api }
    } catch (error) {
      // 换下一个 API 再试
    }
  }
  return { list: [], api: "" }
}

function pickCalendar(allCalendars) {
  const rosters = allCalendars.filter(item => String(item.title || "").includes("排班"))
  if (titleHint) {
    const exact = allCalendars.find(item => String(item.title || "").trim() === titleHint)
    if (exact) return exact

    const matched = rosters.find(item => String(item.title || "").includes(titleHint))
    if (matched) return matched

    // 参数可能填的是姓名（团队日历场景），日历名里没有姓名，继续往下回退
  }
  return rosters.length > 0 ? rosters[0] : null
}

function dateText(date) {
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

function dateRangeText(start, end) {
  if (start.getFullYear() !== end.getFullYear()) {
    return `${start.getFullYear()}年${dateText(start)}–${end.getFullYear()}年${dateText(end)}`
  }
  return `${dateText(start)}–${dateText(end)}`
}

function weekdayText(date) {
  return ["日", "一", "二", "三", "四", "五", "六"][date.getDay()]
}

function addText(stack, text, size, color, weight = "regular") {
  const label = stack.addText(text)
  label.font = Font.systemFont(size)
  if (weight === "bold") label.font = Font.boldSystemFont(size)
  if (weight === "semibold") label.font = Font.semiboldSystemFont(size)
  label.textColor = color
  label.lineLimit = 1
  return label
}

function addHeader(widget, title, detail) {
  const row = widget.addStack()
  row.centerAlignContent()
  const icon = row.addImage(SFSymbol.named("calendar").image)
  icon.imageSize = new Size(16, 16)
  icon.tintColor = new Color(COLOR.today)
  row.addSpacer(6)
  addText(row, title, 15, new Color(COLOR.text), "semibold")
  row.addSpacer()
  addText(row, detail, 11, new Color(COLOR.muted))
}

// 底部图例：班次颜色 + 本月天数（compact 用于小号组件）
function addLegend(widget, counts, compact = false) {
  const legend = widget.addStack()
  legend.centerAlignContent()
  const size = compact ? 9 : 10
  const gap = compact ? 6 : 8
  let first = true
  for (const code of ["早", "晚", "休"]) {
    const shift = SHIFT[code]
    if (!first) legend.addSpacer(gap)
    first = false
    addText(legend, "●", size, shift.color)
    legend.addSpacer(2)
    const label = compact ? shift.label : shift.name
    addText(legend, counts ? `${label} ${counts[code]}` : label, size, new Color(COLOR.muted))
  }
}

function startOfWeek(date) {
  const result = new Date(date)
  const offset = (date.getDay() + 6) % 7 // 周一为一周的第一天
  result.setDate(date.getDate() - offset)
  return atMidnight(result)
}

function displayedMonthForDate(date) {
  const year = date.getFullYear()
  const month = date.getMonth()
  // 从本月最后一天所在周的周一起，提前显示下个月。
  const lastWeekStart = startOfWeek(new Date(year, month + 1, 0))
  const monthOffset = daysBetween(date, lastWeekStart) >= 0 ? 1 : 0
  return new Date(year, month + monthOffset, 1)
}

function addMonthHeader(widget, year, month) {
  const row = widget.addStack()
  row.centerAlignContent()
  const icon = row.addImage(SFSymbol.named("calendar").image)
  icon.imageSize = new Size(16, 16)
  icon.tintColor = new Color(COLOR.today)
  row.addSpacer(6)
  addText(row, `${year}年${month + 1}月`, 16, new Color(COLOR.text), "semibold")
  row.addSpacer()
  const todayShift = shiftFor(today)
  const detail = `今天 ${today.getMonth() + 1}/${today.getDate()} · ${todayShift ? todayShift.name : "暂无排班"}`
  addText(row, detail, 11, new Color(COLOR.today), "semibold")
}

function addWeek(widget) {
  const weekStart = startOfWeek(today)
  const weekEnd = new Date(weekStart)
  weekEnd.setDate(weekStart.getDate() + 6)
  addHeader(widget, "本周排班", dateRangeText(weekStart, weekEnd))
  widget.addSpacer()

  const weekContainer = widget.addStack()
  weekContainer.layoutHorizontally()
  weekContainer.addSpacer()
  const weekRow = weekContainer.addStack()
  weekRow.layoutHorizontally()
  for (let offset = 0; offset < 7; offset++) {
    const date = new Date(weekStart)
    date.setDate(weekStart.getDate() + offset)
    const shift = shiftFor(date)
    const isToday = daysBetween(date, today) === 0
    const day = weekRow.addStack()
    day.layoutVertically()
    day.centerAlignContent()
    day.size = new Size(36, 82)
    day.backgroundColor = new Color(isToday ? COLOR.todayFill : COLOR.card)
    day.cornerRadius = 10
    if (isToday) {
      day.borderWidth = 1.5
      day.borderColor = new Color(COLOR.today)
    }
    day.setPadding(8, 3, 8, 3)
    addText(day, isToday ? "今天" : `周${["一", "二", "三", "四", "五", "六", "日"][offset]}`, 10, isToday ? new Color(COLOR.today) : new Color(COLOR.muted), "semibold")
    day.addSpacer(4)
    addText(day, String(date.getDate()), 18, new Color(COLOR.text), "semibold")
    day.addSpacer(4)
    addText(day, shift ? shift.label : "—", 13, shift ? shift.color : new Color(COLOR.faint), "bold")
    if (offset < 6) weekRow.addSpacer(5)
  }
  weekContainer.addSpacer()
  widget.addSpacer()
  addLegend(widget, monthCounts(today.getFullYear(), today.getMonth()))
}

function addMonth(widget) {
  const year = displayedMonth.getFullYear()
  const month = displayedMonth.getMonth()
  const cellWidth = 40
  const columnSpacing = 3
  addMonthHeader(widget, year, month)
  widget.addSpacer(6)

  const weekdayContainer = widget.addStack()
  weekdayContainer.layoutHorizontally()
  weekdayContainer.addSpacer()
  const weekdayRow = weekdayContainer.addStack()
  weekdayRow.layoutHorizontally()
  const weekdayNames = ["一", "二", "三", "四", "五", "六", "日"]
  for (let index = 0; index < weekdayNames.length; index++) {
    const item = weekdayRow.addStack()
    item.centerAlignContent()
    item.size = new Size(cellWidth, 14)
    addText(item, weekdayNames[index], 11, new Color(COLOR.faint), "semibold")
    if (index < weekdayNames.length - 1) weekdayRow.addSpacer(columnSpacing)
  }
  weekdayContainer.addSpacer()
  widget.addSpacer(3)

  const firstDay = new Date(year, month, 1)
  const leadingDays = (firstDay.getDay() + 6) % 7
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const rowCount = Math.ceil((leadingDays + daysInMonth) / 7)
  const cellHeight = rowCount === 6 ? 42 : rowCount === 5 ? 51 : 65
  const rowSpacing = rowCount === 6 ? 3 : 4

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
    const rowContainer = widget.addStack()
    rowContainer.layoutHorizontally()
    rowContainer.addSpacer()
    const row = rowContainer.addStack()
    row.layoutHorizontally()
    for (let column = 0; column < 7; column++) {
      const dayNumber = rowIndex * 7 + column - leadingDays + 1
      const cell = row.addStack()
      cell.layoutVertically()
      cell.centerAlignContent()
      cell.size = new Size(cellWidth, cellHeight)
      cell.cornerRadius = 7
      cell.setPadding(3, 2, 3, 2)

      const date = new Date(year, month, dayNumber)
      const shift = shiftFor(date)
      const isToday = daysBetween(date, today) === 0
      const isCurrentMonth = date.getMonth() === month

      // 相邻月份淡化显示；今天保留浅蓝背景和蓝色边框。
      if (isToday || isCurrentMonth) {
        cell.backgroundColor = new Color(isToday ? COLOR.todayFill : COLOR.card)
      }
      if (isToday) {
        cell.borderWidth = 1.5
        cell.borderColor = new Color(COLOR.today)
      }
      const isEmphasized = isCurrentMonth || isToday
      const dateColor = new Color(isEmphasized ? COLOR.text : COLOR.faint)
      const shiftColor = shift
        ? isEmphasized ? shift.color : new Color(shift.hex, 0.55)
        : new Color(COLOR.faint, isEmphasized ? 1 : 0.55)
      cell.addSpacer()
      addText(cell, String(date.getDate()), 16, dateColor, "bold")
      cell.addSpacer(3)
      addText(cell, shift ? shift.label : "—", 12, shiftColor, "bold")
      cell.addSpacer()
      if (column < 6) row.addSpacer(columnSpacing)
    }
    rowContainer.addSpacer()
    if (rowIndex < rowCount - 1) widget.addSpacer(rowSpacing)
  }
  widget.addSpacer()
  addLegend(widget, monthCounts(year, month))
}

function addSmall(widget) {
  const todayShift = shiftFor(today)
  addHeader(widget, "我的排班", `${today.getFullYear()}年`)
  widget.addSpacer(12)
  if (todayShift) {
    addText(widget, `今天 · ${dateText(today)} · 周${weekdayText(today)}`, 12, new Color(COLOR.muted))
    widget.addSpacer(4)
    addText(widget, todayShift.name, 25, todayShift.color, "bold")
    if (todayShift.time) {
      widget.addSpacer(2)
      addText(widget, todayShift.time, 13, new Color(COLOR.text), "semibold")
    }
  } else {
    addText(widget, `今天 · ${dateText(today)}`, 12, new Color(COLOR.muted))
    widget.addSpacer(4)
    addText(widget, "暂无排班", 25, SHIFT["休"].color, "bold")
    addText(widget, "请在 ics-roster 排班页面添加", 12, new Color(COLOR.muted))
  }
  widget.addSpacer()
  addLegend(widget, monthCounts(today.getFullYear(), today.getMonth()), true)
}

function addCalendarIssue(widget) {
  const needPerson = calendarIssue === "need-person"
  const calendarMissing = calendarIssue === "calendar-not-found"

  addHeader(widget, "我的排班", needPerson ? "需要指定姓名" : "日历读取失败")
  widget.addSpacer(16)

  const headline = needPerson
    ? "团队日历需要指定名字"
    : calendarMissing
      ? "未找到排班日历"
      : "无法访问系统日历"
  addText(widget, headline, 18, new Color(COLOR.text), "bold")
  widget.addSpacer(6)

  const tip = needPerson
    ? "长按组件 → 编辑小组件 → Parameter 填你的名字"
    : calendarMissing
      ? calendarApi
        ? "日历里没有名字含「排班」的，请在 Parameter 填完整日历名"
        : "请在 Parameter 填日历全名（日历 App 里看到的标题）"
      : "请在系统设置中允许 Scriptable 访问日历"
  addText(widget, tip, 12, new Color(COLOR.muted))
  widget.addSpacer(6)
  addText(widget, WIDGET_VERSION, 9, new Color(COLOR.faint))
  widget.addSpacer(2)

  // 排查信息：能看到的日历名 / 具体报错 / 当前参数
  if (calendarError) {
    addText(widget, `错误：${calendarError}`, 9, new Color(COLOR.faint))
  } else if (calendarNames.length > 0) {
    addText(widget, `可见日历：${calendarNames.slice(0, 3).join("、")}`, 9, new Color(COLOR.faint))
    widget.addSpacer(2)
    addText(widget, `${calendarApi} · ${calendarNames.length} 个 · 参数：${titleHint || "空"}`, 9, new Color(COLOR.faint))
  } else {
    addText(widget, "未能枚举日历，请把 Parameter 填成日历全名", 9, new Color(COLOR.faint))
  }
}

const today = atMidnight(new Date())
const displayedMonth = displayedMonthForDate(today)
try {
  // 参数填了名字时先按标题查（订阅日历是只读日历，不一定能被枚举到）；
  // 只填姓名也能自动补成「姓名 排班」
  let scheduleCalendar = await findCalendarByHint(titleHint)

  const listed = listEventCalendars()
  calendarApi = listed.api
  calendarNames = listed.list.map(item => String(item.title || "")).filter(Boolean)

  if (!scheduleCalendar) scheduleCalendar = pickCalendar(listed.list)

  if (!scheduleCalendar) {
    calendarIssue = "calendar-not-found"
  } else if (String(scheduleCalendar.title || "").includes("团队") && !nameHint) {
    // 团队日历里所有人的班次都在，不指定名字会把别人的班算成自己的
    calendarIssue = "need-person"
  } else {
    calendarTitle = String(scheduleCalendar.title || "")
    const earliestDate = new Date(Math.min(today.getTime(), displayedMonth.getTime()))
    const latestDate = new Date(Math.max(today.getTime(), displayedMonth.getTime()))
    const fetchStart = new Date(earliestDate.getFullYear(), earliestDate.getMonth() - 1, 1)
    const fetchEnd = new Date(latestDate.getFullYear(), latestDate.getMonth() + 2, 1)
    calendarEvents = await CalendarEvent.between(fetchStart, fetchEnd, [scheduleCalendar])
  }
} catch (error) {
  calendarIssue = "calendar-access-denied"
  calendarError = String((error && error.message) || error)
}

const widget = new ListWidget()
widget.backgroundColor = new Color(COLOR.background)
widget.setPadding(14, 14, 14, 14)
const nextMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1, 0, 1)
widget.refreshAfterDate = new Date(Math.min(Date.now() + 30 * 60 * 1000, nextMidnight.getTime()))

const renderFamily = config.widgetFamily || "medium"
if (calendarIssue) addCalendarIssue(widget)
else if (renderFamily === "small") addSmall(widget)
else if (renderFamily === "large") addMonth(widget)
else addWeek(widget)

Script.setWidget(widget)
if (!config.runsInWidget) {
  await widget.presentMedium()
}
Script.complete()
