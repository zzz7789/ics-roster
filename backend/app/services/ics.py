"""ICS（RFC 5545）生成：不依赖第三方库，便于控制输出细节。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models import ShiftType

TZ = ZoneInfo("Asia/Shanghai")
PRODID = "-//ics-roster//Shift Calendar//ZH-CN"


def _escape(text: str) -> str:
    """转义 RFC 5545 规定需要转义的字符。"""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """按 75 字节折行，中文按 UTF-8 字节计算，避免破字。"""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[str] = []
    buf = b""
    limit = 75
    for char in line:
        encoded = char.encode("utf-8")
        if len(buf) + len(encoded) > limit:
            chunks.append(buf.decode("utf-8"))
            buf = b""
            limit = 74  # 续行首部有一个空格
        buf += encoded
    if buf:
        chunks.append(buf.decode("utf-8"))
    return "\r\n ".join(chunks)


def _dt(value: datetime, utc: bool = False) -> str:
    if value.tzinfo is None:
        # 数据库里的时间统一按 UTC 存储（SQLite CURRENT_TIMESTAMP）
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    if utc:
        return value.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
    return value.strftime("%Y%m%dT%H%M%S")


def build_event(
    *,
    uid: str,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
    color: str = "",
    stamp: datetime | None = None,
) -> list[str]:
    stamp = stamp or datetime.now(tz=TZ)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_dt(stamp, utc=True)}",
        f"DTSTART;TZID=Asia/Shanghai:{_dt(start)}",
        f"DTEND;TZID=Asia/Shanghai:{_dt(end)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if color:
        # 非标准但对多数客户端友好的颜色提示（Apple 日历读取 X-APPLE 字段）
        lines.append(f"COLOR:{color}")
    lines.append("TRANSP:OPAQUE")
    lines.append("END:VEVENT")
    return lines


def is_all_day(shift_type: ShiftType) -> bool:
    """没有起止时间的班次（如休息）按全天事件输出。"""
    return not shift_type.start_time and not shift_type.end_time


def build_all_day_event(
    *,
    uid: str,
    summary: str,
    day: date,
    description: str = "",
    color: str = "",
    stamp: datetime | None = None,
) -> list[str]:
    """全天事件：DTSTART/DTEND 用 VALUE=DATE，DTEND 为次日（RFC 5545 约定，右开区间）。"""
    stamp = stamp or datetime.now(tz=TZ)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_dt(stamp, utc=True)}",
        f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
        f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if color:
        lines.append(f"COLOR:{color}")
    # 休息这类全天事项不占用「忙碌」状态
    lines.append("TRANSP:TRANSPARENT")
    lines.append("END:VEVENT")
    return lines


def event_times(work_date: date, shift_type: ShiftType) -> tuple[datetime, datetime] | None:
    """把「日期 + 班次类型」换算成起止时间；休息类返回 None。"""
    if not shift_type.emit_to_calendar:
        return None
    try:
        start_t = time.fromisoformat(shift_type.start_time) if shift_type.start_time else time(8, 0)
        end_t = time.fromisoformat(shift_type.end_time) if shift_type.end_time else time(16, 0)
    except ValueError:
        return None
    start = datetime.combine(work_date, start_t, tzinfo=TZ)
    end_date = work_date + timedelta(days=1) if shift_type.ends_next_day else work_date
    end = datetime.combine(end_date, end_t, tzinfo=TZ)
    if end <= start:
        end = start + timedelta(hours=8)
    return start, end


def build_calendar(events: list[list[str]], cal_name: str) -> str:
    now = datetime.now(tz=TZ)
    head = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(cal_name)}",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    body: list[str] = build_vtimezone()
    for event in events:
        body.extend(event)
    tail = ["END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in head + body + tail) + "\r\n"


def build_vtimezone() -> list[str]:
    """中国无夏令时，提供固定 +08:00 的时区定义，兼容严格的客户端。"""
    return [
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
