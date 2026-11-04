"""ICS（RFC 5545）解析与重复规则展开。

设计目标：只覆盖排班场景真正会用到的子集，保持零第三方依赖。
- 折行还原（续行以空格或 tab 开头）
- DTSTART / DTEND 三种写法：`;TZID=`、`;VALUE=DATE`（全天）、以 `Z` 结尾的 UTC
- RRULE：FREQ=DAILY|WEEKLY|MONTHLY，配合 INTERVAL / COUNT / UNTIL / BYDAY
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")

# 单次导入最多展开的事件数，防止畸形 RRULE 把服务打满
MAX_OCCURRENCES = 2000
# 允许的最大展开跨度（天）
MAX_SPAN_DAYS = 1100

WEEKDAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


class IcsParseError(ValueError):
    """ICS 内容无法解析时抛出，接口层转成 400。"""


@dataclass
class ParsedEvent:
    uid: str = ""
    summary: str = ""
    description: str = ""
    location: str = ""
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    rrule: str = ""
    skipped: str = ""  # 跳过原因，便于前端提示


@dataclass
class Occurrence:
    """一次具体发生：某天、某时段。"""

    work_date: date
    start: datetime
    end: datetime
    all_day: bool
    summary: str
    description: str = ""


@dataclass
class ParseResult:
    events: list[ParsedEvent] = field(default_factory=list)
    calendar_name: str = ""
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 词法层


def unfold(text: str) -> list[str]:
    """还原被折行的内容行。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in normalized.split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def parse_content_line(line: str) -> tuple[str, dict[str, str], str]:
    """把 `NAME;PARAM=V:VALUE` 拆成 (name, params, value)。"""
    # 参数区与值之间以第一个未加引号的冒号分隔
    in_quotes = False
    split_at = -1
    for idx, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ":" and not in_quotes:
            split_at = idx
            break
    if split_at < 0:
        return line.strip().upper(), {}, ""

    head, value = line[:split_at], line[split_at + 1 :]
    segments = _split_unescaped(head, ";")
    name = segments[0].strip().upper()
    params: dict[str, str] = {}
    for segment in segments[1:]:
        if "=" not in segment:
            continue
        key, _, val = segment.partition("=")
        params[key.strip().upper()] = val.strip().strip('"')
    return name, params, value


def _split_unescaped(text: str, sep: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            buf.append(char)
        elif char == sep and not in_quotes:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    out.append("".join(buf))
    return out


def unescape_text(value: str) -> str:
    """还原 TEXT 类型值里的转义。"""
    out: list[str] = []
    idx = 0
    while idx < len(value):
        char = value[idx]
        if char == "\\" and idx + 1 < len(value):
            nxt = value[idx + 1]
            out.append("\n" if nxt in ("n", "N") else nxt)
            idx += 2
            continue
        out.append(char)
        idx += 1
    return "".join(out)


# ---------------------------------------------------------------- 时间解析

_DATE_ONLY = re.compile(r"^(\d{8})$")
_DATE_TIME = re.compile(r"^(\d{8})T(\d{6})(Z)?$", re.IGNORECASE)


def parse_dt(value: str, params: dict[str, str]) -> tuple[datetime, bool]:
    """返回 (时间, 是否全天)。无法识别时抛 IcsParseError。"""
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or _DATE_ONLY.match(value):
        match = _DATE_ONLY.match(value)
        if not match:
            raise IcsParseError(f"无法识别的日期：{value}")
        day = datetime.strptime(match.group(1), "%Y%m%d").date()
        return datetime.combine(day, time(0, 0), tzinfo=TZ), True

    match = _DATE_TIME.match(value)
    if not match:
        raise IcsParseError(f"无法识别的时间：{value}")
    stamp = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    if match.group(3):  # 以 Z 结尾，UTC
        return stamp.replace(tzinfo=UTC).astimezone(TZ), False
    tzid = params.get("TZID", "").strip()
    if tzid:
        try:
            return stamp.replace(tzinfo=ZoneInfo(tzid)).astimezone(TZ), False
        except Exception:  # 未知时区退化为本地（中国无夏令时，误差可接受）
            return stamp.replace(tzinfo=TZ), False
    # 浮动时间：按本地时间理解
    return stamp.replace(tzinfo=TZ), False


# ---------------------------------------------------------------- 主解析


def parse_ics(text: str) -> ParseResult:
    if "BEGIN:VCALENDAR" not in text.upper():
        raise IcsParseError("不是有效的 ICS：缺少 BEGIN:VCALENDAR")

    result = ParseResult()
    if "ENCODING=BASE64" in text.upper():
        result.warnings.append("检测到二进制属性（如 ATTACH），已忽略")

    current: dict[str, tuple[dict[str, str], str]] | None = None
    for line in unfold(text):
        name, params, value = parse_content_line(line)
        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            current = {}
            continue
        if name == "END" and value.strip().upper() == "VEVENT":
            if current is not None:
                result.events.append(_build_event(current))
            current = None
            continue
        if current is not None:
            current[name] = (params, value)
            continue
        if name == "X-WR-CALNAME":
            result.calendar_name = unescape_text(value).strip()
        elif name == "RRULE":
            pass  # VCALENDAR 级的 RRULE 不存在，忽略

    if not result.events:
        result.warnings.append("文件里没有 VEVENT")
    return result


def _build_event(fields: dict[str, tuple[dict[str, str], str]]) -> ParsedEvent:
    event = ParsedEvent()
    if "SUMMARY" in fields:
        event.summary = unescape_text(fields["SUMMARY"][1]).strip()
    if "DESCRIPTION" in fields:
        event.description = unescape_text(fields["DESCRIPTION"][1]).strip()
    if "LOCATION" in fields:
        event.location = unescape_text(fields["LOCATION"][1]).strip()
    if "UID" in fields:
        event.uid = fields["UID"][1].strip()
    if "RRULE" in fields:
        event.rrule = fields["RRULE"][1].strip()

    if "DTSTART" not in fields:
        event.skipped = "缺少 DTSTART"
        return event
    try:
        start_params, start_value = fields["DTSTART"]
        start, all_day = parse_dt(start_value, start_params)
    except IcsParseError as exc:
        event.skipped = str(exc)
        return event

    event.start = start
    event.all_day = all_day
    if "DTEND" in fields:
        try:
            end_params, end_value = fields["DTEND"]
            end, _ = parse_dt(end_value, end_params)
            event.end = end
        except IcsParseError:
            event.end = start + (timedelta(days=1) if all_day else timedelta(hours=8))
    elif "DURATION" in fields:
        parsed = _parse_duration(fields["DURATION"][1])
        event.end = start + (parsed or (timedelta(days=1) if all_day else timedelta(hours=8)))
    else:
        event.end = start + (timedelta(days=1) if all_day else timedelta(hours=8))
    return event


def _parse_duration(value: str) -> timedelta:
    match = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$", value.strip(), re.IGNORECASE)
    if not match:
        return timedelta(hours=8)
    days, hours, minutes = (int(x) if x else 0 for x in match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes)


# ---------------------------------------------------------------- RRULE 展开


def _parse_rrule(value: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for chunk in value.split(";"):
        if "=" not in chunk:
            continue
        key, _, val = chunk.partition("=")
        parts[key.strip().upper()] = val.strip().upper()
    return parts


def expand_event(
    event: ParsedEvent, window_start: date | None = None, window_end: date | None = None
) -> list[Occurrence]:
    """把事件（含 RRULE）展开成具体日期列表。"""
    if event.skipped or event.start is None or event.end is None:
        return []

    duration = event.end - event.start
    starts = _expand_starts(event, window_start, window_end)
    out: list[Occurrence] = []
    for start in starts:
        out.append(
            Occurrence(
                work_date=start.date(),
                start=start,
                end=start + duration,
                all_day=event.all_day,
                summary=event.summary,
                description=event.description,
            )
        )
    return out


def _expand_starts(
    event: ParsedEvent, window_start: date | None, window_end: date | None
) -> list[datetime]:
    start: datetime = event.start  # type: ignore[assignment]
    if not event.rrule:
        return [start]

    rule = _parse_rrule(event.rrule)
    freq = rule.get("FREQ", "")
    if freq not in ("DAILY", "WEEKLY", "MONTHLY"):
        # 其余频率（YEARLY / HOURLY / SECONDLY…）在排班场景罕见，只保留首次
        return [start]

    interval = max(1, int(rule["INTERVAL"])) if rule.get("INTERVAL", "").isdigit() else 1
    count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else 0
    until: datetime | None = None
    if rule.get("UNTIL"):
        try:
            until, _ = parse_dt(rule["UNTIL"], {})
        except IcsParseError:
            until = None
    byday = [WEEKDAY_CODES[c] for c in rule.get("BYDAY", "").split(",") if c[-2:] in WEEKDAY_CODES]

    lower = start.date()
    if window_start:
        lower = max(lower, window_start)
    upper = window_end or (start.date() + timedelta(days=MAX_SPAN_DAYS))

    results: list[datetime] = []
    produced = 0
    cursor = start
    guard = 0
    while guard < MAX_OCCURRENCES * 4:
        guard += 1
        if count and produced >= count:
            break
        if until and cursor > until:
            break
        if cursor.date() > upper:
            break

        if freq == "WEEKLY" and byday:
            # 从周一为基准的一周内，逐天判断
            week_start = cursor - timedelta(days=cursor.weekday())
            matching = sorted(
                week_start + timedelta(days=offset) for offset in byday
            )
            advance_to_next_week = True
            for candidate in matching:
                if candidate < cursor:
                    continue
                if count and produced >= count:
                    break
                if until and candidate > until:
                    break
                if candidate.date() > upper:
                    break
                produced += 1
                if candidate.date() >= lower:
                    results.append(candidate)
            if advance_to_next_week:
                cursor = week_start + timedelta(weeks=interval)
        else:
            if cursor.date() >= lower:
                produced += 1
                results.append(cursor)
            else:
                produced += 1
            if freq == "DAILY":
                cursor += timedelta(days=interval)
            elif freq == "WEEKLY":
                cursor += timedelta(weeks=interval)
            else:  # MONTHLY
                cursor = _add_months(cursor, interval)
        if len(results) >= MAX_OCCURRENCES:
            break
    return results


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return value.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day
