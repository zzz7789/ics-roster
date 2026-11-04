"""ICS 文件导入：先预览分组与建议映射，确认后再落库。

导入是「宽进」的：能识别就用，识别不了的交给前端人工指定，
不因为一条怪数据整份文件失败。
"""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import Person, Shift, ShiftType
from ..schemas import (
    ExcelApplyOut,
    ExcelPersonOut,
    ExcelPreviewOut,
    ExcelSheetOut,
    ImportApplyOut,
    ImportGroup,
    ImportPreviewOut,
)
from ..services.ics_import import (
    Occurrence,
    ParseResult,
    expand_event,
    parse_ics,
)
from ..services.xlsx_import import ExcelParseError, parse_xlsx

router = APIRouter(
    prefix="/api/import", tags=["import"], dependencies=[Depends(require_user)]
)

MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_HORIZON_DAYS = 366


def _group_key(occ: Occurrence) -> str:
    """同一 SUMMARY + 同一时间形态，视为同一个「映射组」。"""
    kind = "allday" if occ.all_day else f"{occ.start:%H:%M}-{occ.end:%H:%M}"
    return f"{occ.summary.strip() or '(无标题)'}|{kind}"


def _read_files(files: list[UploadFile]) -> tuple[list[Occurrence], list[str], str]:
    occurrences: list[Occurrence] = []
    warnings: list[str] = []
    names: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        raw = upload.file.read()
        if len(raw) > MAX_FILE_BYTES:
            warnings.append(f"{upload.filename}：超过 8MB，已跳过")
            continue
        text = _decode(raw)
        try:
            parsed: ParseResult = parse_ics(text)
        except ValueError as exc:
            warnings.append(f"{upload.filename}：{exc}")
            continue
        if parsed.calendar_name:
            names.append(parsed.calendar_name)
        warnings.extend(f"{upload.filename}：{w}" for w in parsed.warnings)

        horizon = date.today() + timedelta(days=DEFAULT_HORIZON_DAYS * 3)
        kept = 0
        for event in parsed.events:
            if event.skipped:
                warnings.append(f"{upload.filename}：跳过一条事件（{event.skipped}）")
                continue
            for occ in expand_event(event, None, horizon):
                occurrences.append(occ)
                kept += 1
        if not kept:
            warnings.append(f"{upload.filename}：没有可导入的事件")
    return occurrences, warnings, "、".join(names)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fmt_time(occ: Occurrence) -> str:
    if occ.all_day:
        return "全天"
    return f"{occ.start:%H:%M}-{occ.end:%H:%M}"


def _suggest_person(summary: str, persons: list[Person]) -> tuple[int | None, str | None]:
    """在标题里找已有人员名，取最长的匹配。"""
    hits = [p for p in persons if p.name and p.name in summary]
    if not hits:
        return None, None
    best = max(hits, key=lambda p: len(p.name))
    return best.id, best.name


def _suggest_type(occ: Occurrence, types: list[ShiftType]) -> tuple[int | None, str | None]:
    summary = occ.summary
    if summary.strip():
        by_name = [t for t in types if t.name and t.name in summary]
        if by_name:
            best = max(by_name, key=lambda t: len(t.name))
            return best.id, best.name

    if occ.all_day:
        rest = next((t for t in types if not t.emit_to_calendar), None)
        return (rest.id, rest.name) if rest else (None, None)

    start_hm, end_hm = occ.start.strftime("%H:%M"), occ.end.strftime("%H:%M")
    for candidate in types:
        if not candidate.start_time or not candidate.end_time:
            continue
        if candidate.start_time == start_hm and candidate.end_time == end_hm:
            return candidate.id, candidate.name
    return None, None


def _guess_person_name(summary: str, type_name: str | None) -> str:
    """从「张 三 早班」这类标题里猜一个新建人员名。"""
    text = summary
    if type_name:
        text = text.replace(type_name, "")
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    parts = [p.strip() for p in re.split(r"[\s\-—_/,|:：]+", text) if p.strip()]
    return parts[0][:32] if parts else ""


@router.post("/ics/preview", response_model=ImportPreviewOut)
def preview_ics(
    files: list[UploadFile] = File(..., description="一个或多个 .ics 文件"),
    db: Session = Depends(get_db),
):
    """只解析不落库，返回按「标题 + 时段」聚合的分组与建议映射。"""
    occurrences, warnings, calendar_names = _read_files(files)
    if not occurrences:
        raise HTTPException(status_code=400, detail="；".join(warnings) or "没有可导入的事件")

    persons = list(db.scalars(select(Person).where(Person.active.is_(True))).all())
    types = list(db.scalars(select(ShiftType)).all())

    buckets: "OrderedDict[str, list[Occurrence]]" = OrderedDict()
    for occ in occurrences:
        buckets.setdefault(_group_key(occ), []).append(occ)

    groups: list[ImportGroup] = []
    for key, items in buckets.items():
        items.sort(key=lambda o: o.start)
        sample = items[0]
        person_id, person_name = _suggest_person(sample.summary, persons)
        type_id, type_name = _suggest_type(sample, types)
        groups.append(
            ImportGroup(
                key=key,
                summary=sample.summary or "(无标题)",
                time_label=_fmt_time(sample),
                all_day=sample.all_day,
                count=len(items),
                first_date=items[0].work_date,
                last_date=items[-1].work_date,
                suggested_person_id=person_id,
                suggested_person_name=person_name,
                suggested_new_person_name=(
                    "" if person_id else _guess_person_name(sample.summary, type_name)
                ),
                suggested_shift_type_id=type_id,
                suggested_shift_type_name=type_name,
            )
        )

    return ImportPreviewOut(
        groups=groups,
        warnings=warnings,
        calendar_names=calendar_names,
        total_events=sum(g.count for g in groups),
    )


@router.post("/ics/apply", response_model=ImportApplyOut)
def apply_ics(
    files: list[UploadFile] = File(...),
    mapping: str = Form(..., description="JSON: {group_key: {person_id|new_person_name, shift_type_id}}"),
    db: Session = Depends(get_db),
):
    """按前端确认的映射落库，同人同天覆盖。"""
    try:
        decisions: dict[str, dict] = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"mapping 不是合法 JSON：{exc}") from exc
    if not isinstance(decisions, dict):
        raise HTTPException(status_code=400, detail="mapping 必须是对象")

    occurrences, warnings, _ = _read_files(files)
    if not occurrences:
        raise HTTPException(status_code=400, detail="；".join(warnings) or "没有可导入的事件")

    created_by_person: dict[int, Person] = {}
    created = updated = skipped = 0
    unknown_keys: set[str] = set()

    for occ in occurrences:
        key = _group_key(occ)
        decision = decisions.get(key)
        if not decision:
            skipped += 1
            unknown_keys.add(key)
            continue

        person = _resolve_person(db, decision, created_by_person)
        type_id = decision.get("shift_type_id")
        if person is None or not type_id:
            skipped += 1
            continue
        shift_type = db.get(ShiftType, int(type_id))
        if not shift_type:
            skipped += 1
            continue

        existing = db.scalar(
            select(Shift).where(
                Shift.person_id == person.id, Shift.work_date == occ.work_date
            )
        )
        if existing:
            if existing.shift_type_id == shift_type.id:
                skipped += 1  # 完全重复，保持幂等
                continue
            existing.shift_type_id = shift_type.id
            if occ.description and not existing.note:
                existing.note = occ.description[:255]
            updated += 1
        else:
            db.add(
                Shift(
                    person_id=person.id,
                    shift_type_id=shift_type.id,
                    work_date=occ.work_date,
                    note=(occ.description or "")[:255],
                )
            )
            created += 1

    db.commit()
    if unknown_keys:
        warnings.append(f"{len(unknown_keys)} 个分组未指定映射，已跳过")
    return ImportApplyOut(
        created=created, updated=updated, skipped=skipped, warnings=warnings
    )


def _resolve_person(
    db: Session, decision: dict, cache: dict[int, Person]
) -> Person | None:
    person_id = decision.get("person_id")
    if person_id:
        cached = cache.get(int(person_id))
        if cached:
            return cached
        person = db.get(Person, int(person_id))
        if person:
            cache[person.id] = person
        return person

    new_name = (decision.get("new_person_name") or "").strip()
    if not new_name:
        return None
    existing = db.scalar(select(Person).where(Person.name == new_name))
    if existing:
        cache[existing.id] = existing
        return existing
    person = Person(name=new_name[:64], color=_pick_color(len(cache)))
    db.add(person)
    db.flush()  # 立刻拿到 id，供后续事件复用
    cache[person.id] = person
    return person


PALETTE = ["#4f8cff", "#22c55e", "#f5a524", "#ef4444", "#7c5cff", "#06b6d4", "#ec4899", "#84cc16"]


def _pick_color(index: int) -> str:
    return PALETTE[index % len(PALETTE)]


# ----------------------------- Excel 导入 -----------------------------

MAX_EXCEL_BYTES = 16 * 1024 * 1024


def _suggest_type_for_label(label: str, types: list[ShiftType]) -> int | None:
    """把「早」「休」这类单元格文字映射到班次类型。"""
    text = label.strip()
    if not text:
        return None
    for candidate in types:
        if candidate.name == text:
            return candidate.id
    for candidate in types:
        if candidate.name and (candidate.name in text or text in candidate.name):
            return candidate.id
    return None


@router.post("/excel/preview", response_model=ExcelPreviewOut)
def preview_excel(
    files: list[UploadFile] = File(..., description="一个或多个 .xlsx 排班表"),
    db: Session = Depends(get_db),
):
    """解析 Excel 排班表，返回年月、人员与班次标签的建议映射（不落库）。"""
    active = list(db.scalars(select(Person).where(Person.active.is_(True))).all())
    by_name = {p.name: p for p in active}
    types = list(db.scalars(select(ShiftType)).all())

    sheets: list[ExcelSheetOut] = []
    warnings: list[str] = []
    for upload in files:
        filename = upload.filename or "未命名.xlsx"
        raw = upload.file.read()
        if len(raw) > MAX_EXCEL_BYTES:
            warnings.append(f"{filename}：超过 16MB，已跳过")
            continue
        try:
            parsed = parse_xlsx(raw, filename)
        except ExcelParseError as exc:
            warnings.append(f"{filename}：{exc}")
            continue

        people_out: list[ExcelPersonOut] = []
        for row in parsed.people:
            counts: dict[str, int] = {}
            for label in row.cells.values():
                counts[label] = counts.get(label, 0) + 1
            matched = by_name.get(row.name)
            people_out.append(
                ExcelPersonOut(
                    name=row.name,
                    person_id=matched.id if matched else None,
                    counts=counts,
                    day_count=len(row.cells),
                )
            )

        sheets.append(
            ExcelSheetOut(
                filename=filename,
                sheet_name=parsed.sheet_name,
                title=parsed.title,
                year=parsed.year,
                month=parsed.month,
                date_matched=parsed.date_matched,
                day_count=len(parsed.days),
                shift_labels=parsed.shift_labels,
                label_suggestions={
                    label: _suggest_type_for_label(label, types) for label in parsed.shift_labels
                },
                people=people_out,
                warnings=parsed.warnings,
            )
        )

    if not sheets:
        raise HTTPException(status_code=400, detail="；".join(warnings) or "没有可导入的工作表")
    return ExcelPreviewOut(sheets=sheets, warnings=warnings)


@router.post("/excel/apply", response_model=ExcelApplyOut)
def apply_excel(
    files: list[UploadFile] = File(...),
    options: str = Form(
        ...,
        description='JSON: {shift_map: {"早": 1}, person_map: {"张三": {"person_id": 3}}, year?, month?}',
    ),
    db: Session = Depends(get_db),
):
    """按确认的映射把 Excel 排班落库，同人同天覆盖。"""
    try:
        opts = json.loads(options)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"options 不是合法 JSON：{exc}") from exc

    shift_map = {
        str(label): int(type_id)
        for label, type_id in (opts.get("shift_map") or {}).items()
        if type_id
    }
    person_map: dict[str, dict] = opts.get("person_map") or {}
    year_override = opts.get("year")
    month_override = opts.get("month")

    created = updated = skipped = persons_created = 0
    warnings: list[str] = []
    person_cache: dict[int, Person] = {}
    color_seed = 0

    for upload in files:
        filename = upload.filename or "未命名.xlsx"
        raw = upload.file.read()
        try:
            parsed = parse_xlsx(raw, filename)
        except ExcelParseError as exc:
            warnings.append(f"{filename}：{exc}")
            continue

        year = int(year_override or parsed.year)
        month = int(month_override or parsed.month)

        for row in parsed.people:
            decision = person_map.get(row.name) or {}
            person, was_created = _resolve_excel_person(db, row.name, decision, person_cache)
            if person is None:
                skipped += len(row.cells)
                continue
            if was_created:
                persons_created += 1
            color_seed += 1

            for day, label in row.cells.items():
                type_id = shift_map.get(label)
                if not type_id:
                    skipped += 1
                    continue
                shift_type = db.get(ShiftType, type_id)
                if not shift_type:
                    skipped += 1
                    continue
                try:
                    work_date = date(year, month, day)
                except ValueError:
                    skipped += 1
                    continue

                existing = db.scalar(
                    select(Shift).where(
                        Shift.person_id == person.id, Shift.work_date == work_date
                    )
                )
                if existing:
                    if existing.shift_type_id == shift_type.id:
                        skipped += 1
                        continue
                    existing.shift_type_id = shift_type.id
                    updated += 1
                else:
                    db.add(
                        Shift(
                            person_id=person.id,
                            shift_type_id=shift_type.id,
                            work_date=work_date,
                        )
                    )
                    created += 1

    db.commit()
    return ExcelApplyOut(
        created=created,
        updated=updated,
        skipped=skipped,
        persons_created=persons_created,
        warnings=warnings,
    )


def _resolve_excel_person(
    db: Session, name: str, decision: dict, cache: dict[int, Person]
) -> tuple[Person | None, bool]:
    """返回 (人员, 是否本次新建)。"""
    person_id = decision.get("person_id")
    if person_id:
        cached = cache.get(int(person_id))
        if cached:
            return cached, False
        person = db.get(Person, int(person_id))
        if person:
            cache[person.id] = person
        return person, False

    existing = db.scalar(select(Person).where(Person.name == name))
    if existing:
        cache.setdefault(existing.id, existing)
        return existing, False

    person = Person(name=name[:64], color=_pick_color(len(cache) + 3))
    db.add(person)
    db.flush()
    cache[person.id] = person
    return person, True
