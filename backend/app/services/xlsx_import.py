"""XLSX 排班表解析（零依赖：zipfile + ElementTree）。

针对「一人一行、一天一列」的月度排班表：

    | 序列 | 姓名 | 周一 | 周二 | ... | 晚班 | 休息 |
    |  1   | 张三 |  早  |  晚  | ... |  11  |  8   |
    |  2   | 李四 |  休  |  早  | ... |      |      |

关键点：
- 表头行通过「姓名」字样定位，日号行取表头上一行
- 只保留表头是星期的列，天然排除「晚班/休息」这类统计列
- 年份与月份不写死在表里，用「日号 + 星期」反推，避免跨年出错
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_RNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

MAX_ROWS = 400
MAX_COLS = 80

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
# 允许表头写成 一 / 星期一 / 周一 / Mon 等写法
_WEEKDAY_CHAR = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
WEEKDAY_ALIASES: dict[str, int] = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6,
}

# 常见的休息/无班标记，用于识别「小计行」并跳过
NON_NAME_LABELS = {"早", "晚", "休", "夜", "白", "中", "早班", "晚班", "夜班", "休息", "合计", "小计"}


class ExcelParseError(ValueError):
    """表格结构无法识别时抛出，接口层转 400。"""


@dataclass
class PersonRow:
    name: str
    cells: dict[int, str] = field(default_factory=dict)  # day -> 班次标签


@dataclass
class ParsedRoster:
    sheet_name: str = ""
    title: str = ""
    year: int = 0
    month: int = 0
    date_matched: bool = False
    days: list[dict] = field(default_factory=list)  # [{"day": 2, "weekday": 0, "iso": "2026-11-02"}]
    people: list[PersonRow] = field(default_factory=list)
    shift_labels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- xlsx 读取


def _col_to_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref)
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _sheet_files(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """返回 [(sheet 名, zip 内路径)]，按工作簿顺序。"""
    names = archive.namelist()
    if "xl/workbook.xml" not in names:
        raise ExcelParseError("不是有效的 xlsx：缺少 xl/workbook.xml")

    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        for rel in rel_root.iter(f"{PKG_RNS}Relationship"):
            target = rel.get("Target", "")
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            rels[rel.get("Id", "")] = target

    out: list[tuple[str, str]] = []
    for sheet in workbook.iter(f"{NS}sheet"):
        rid = sheet.get(f"{RNS}id", "")
        path = rels.get(rid)
        if path and path in names:
            out.append((sheet.get("name", ""), path))
    if not out:
        candidates = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))
        if not candidates:
            raise ExcelParseError("xlsx 里没有工作表")
        out = [("Sheet1", candidates[0])]
    return out


def _read_rows(archive: zipfile.ZipFile, path: str) -> dict[int, dict[int, str]]:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))

    sheet = ET.fromstring(archive.read(path))
    rows: dict[int, dict[int, str]] = {}
    for row in sheet.iter(f"{NS}row"):
        row_index = int(row.get("r", "0")) - 1
        if row_index >= MAX_ROWS:
            break
        cells: dict[int, str] = {}
        for cell in row.findall(f"{NS}c"):
            ref = cell.get("r", "")
            col = _col_to_index(ref)
            if col >= MAX_COLS:
                continue
            kind = cell.get("t")
            value_node = cell.find(f"{NS}v")
            inline = cell.find(f"{NS}is")
            value = ""
            if kind == "s" and value_node is not None and value_node.text is not None:
                idx = int(value_node.text)
                value = shared[idx] if idx < len(shared) else ""
            elif kind == "inlineStr" and inline is not None:
                value = "".join(t.text or "" for t in inline.iter(f"{NS}t"))
            elif value_node is not None and value_node.text is not None:
                value = value_node.text
            value = value.strip()
            if value:
                cells[col] = value
        if cells:
            rows[row_index] = cells
    return rows


# ---------------------------------------------------------------- 结构识别


def _weekday_of(text: str) -> int | None:
    cleaned = text.strip().upper()
    if cleaned in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[cleaned]
    # 周一 / 星期一 / 週三 / 礼拜天
    match = re.search(r"(?:周|週|星期|礼拜|禮拜)\s*([一二三四五六日天])", cleaned)
    if match:
        return _WEEKDAY_CHAR[match.group(1)]
    if cleaned in _WEEKDAY_CHAR:
        return _WEEKDAY_CHAR[cleaned]
    return None


def _find_header(rows: dict[int, dict[int, str]]) -> tuple[int, int]:
    """找到含「姓名」的表头行，返回 (行号, 姓名列号)。"""
    for row_index in sorted(rows):
        for col, value in rows[row_index].items():
            if value.strip() in ("姓名", "名字", "人员", "员工"):
                return row_index, col
    raise ExcelParseError("没找到表头行（需要包含「姓名」列）")


def _collect_day_columns(
    rows: dict[int, dict[int, str]], header_row: int, name_col: int
) -> list[tuple[int, int, int]]:
    """返回 [(列号, 日, 星期索引)]。"""
    header = rows.get(header_row, {})
    day_row = rows.get(header_row - 1, {})
    out: list[tuple[int, int, int]] = []
    for col in sorted(header):
        if col <= name_col:
            continue
        weekday = _weekday_of(header[col])
        if weekday is None:
            continue  # 统计列（晚班/休息）在这里被排除
        raw_day = day_row.get(col, "")
        if not raw_day.isdigit():
            digits = re.findall(r"\d+", raw_day)
            if not digits:
                continue
            raw_day = digits[-1]
        day = int(raw_day)
        if not 1 <= day <= 31:
            continue
        out.append((col, day, weekday))
    return out


def _collect_people(
    rows: dict[int, dict[int, str]],
    header_row: int,
    name_col: int,
    day_cols: list[tuple[int, int, int]],
) -> list[PersonRow]:
    people: list[PersonRow] = []
    for row_index in sorted(rows):
        if row_index <= header_row:
            continue
        cells = rows[row_index]
        name = cells.get(name_col, "").strip()
        lineup = {col: cells.get(col, "") for col, _, _ in day_cols}
        if not name:
            # 小计行（A 列写「早/晚/休」）或空行，到此为止
            if any(v for v in lineup.values()) and all(
                v in NON_NAME_LABELS for v in lineup.values() if v
            ):
                break
            continue
        if name in NON_NAME_LABELS:
            break
        if not any(lineup.values()):
            continue
        people.append(
            PersonRow(name=name, cells={day: lineup[col] for col, day, _ in day_cols if lineup[col]})
        )
    return people


def _infer_year_month(
    day_cols: list[tuple[int, int, int]], hints: str
) -> tuple[int, int, bool]:
    """用「日号 + 星期」反推年月，hints 为标题/文件名里的月份线索。"""
    today = date.today()
    month_hint = None
    match = re.search(r"(\d{1,2})\s*[月.]\s*\d{1,2}", hints)
    if match and 1 <= int(match.group(1)) <= 12:
        month_hint = int(match.group(1))

    candidate_months = [month_hint] if month_hint else list(range(1, 13))
    candidate_years = [today.year - 1, today.year, today.year + 1]

    fallback: tuple[int, int] | None = None
    for year in candidate_years:
        for month in candidate_months:
            if all(_safe_date(year, month, day).weekday() == weekday for _, day, weekday in day_cols):
                return year, month, True
            if fallback is None:
                fallback = (year, month)
    if fallback is None:
        fallback = (today.year, month_hint or today.month)
    return fallback[0], fallback[1], False


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


def parse_xlsx(raw: bytes, filename: str = "") -> ParsedRoster:
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ExcelParseError("不是有效的 xlsx 文件（可能是旧版 .xls，请另存为 .xlsx）") from exc

    result = ParsedRoster()
    with archive:
        sheets = _sheet_files(archive)
        last_error: Exception | None = None
        for sheet_name, path in sheets[:6]:
            try:
                rows = _read_rows(archive, path)
                if not rows:
                    continue
                header_row, name_col = _find_header(rows)
                day_cols = _collect_day_columns(rows, header_row, name_col)
                if len(day_cols) < 2:
                    last_error = ExcelParseError(f"工作表「{sheet_name}」没识别出日期列")
                    continue
                people = _collect_people(rows, header_row, name_col, day_cols)
                if not people:
                    last_error = ExcelParseError(f"工作表「{sheet_name}」没识别出人员行")
                    continue

                title = rows.get(0, {}).get(0, "")
                hints = f"{title} {sheet_name} {filename}"
                year, month, matched = _infer_year_month(day_cols, hints)

                result.sheet_name = sheet_name
                result.title = title
                result.year, result.month, result.date_matched = year, month, matched
                result.people = people
                labels: list[str] = []
                days: list[dict] = []
                for _, day, weekday in day_cols:
                    days.append(
                        {
                            "day": day,
                            "weekday": weekday,
                            "iso": _safe_date(year, month, day).isoformat(),
                        }
                    )
                result.days = days
                for person in people:
                    for label in person.cells.values():
                        if label not in labels:
                            labels.append(label)
                result.shift_labels = labels

                if not matched:
                    result.warnings.append(
                        f"按日号与星期无法唯一确定年月，已猜测为 {year}-{month:02d}，请核对"
                    )
                if not title:
                    result.warnings.append("未找到表头标题（A1），年月由星期推断")
                break
            except ExcelParseError as exc:
                last_error = exc
                continue

        if not result.people:
            raise last_error or ExcelParseError("没识别出有效的排班表")

    return result
