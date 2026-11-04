"""ICS 订阅接口：团队整表订阅 + 单人订阅。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import TEAM_FEED_TOKEN
from ..db import get_db
from ..models import Person, Shift
from ..services.ics import build_calendar, build_event, event_times

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

ICS_MEDIA_TYPE = "text/calendar; charset=utf-8"


def _default_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """未指定区间时默认取前后各一年，保证订阅地址长期有效。"""
    today = date.today()
    return date_from or (today - timedelta(days=180)), date_to or (today + timedelta(days=365))


def _load_shifts(
    db: Session,
    date_from: date | None,
    date_to: date | None,
    person_id: int | None = None,
    *,
    only_active: bool = True,
) -> list[Shift]:
    start, end = _default_range(date_from, date_to)
    stmt = (
        select(Shift)
        .options(joinedload(Shift.shift_type), joinedload(Shift.person))
        .where(Shift.work_date >= start, Shift.work_date <= end)
        .order_by(Shift.work_date)
    )
    if person_id is not None:
        stmt = stmt.where(Shift.person_id == person_id)
    if only_active:
        stmt = stmt.join(Person, Shift.person_id == Person.id).where(Person.active.is_(True))
    return list(db.scalars(stmt).all())


def _render(shifts: list[Shift], multi_person: bool) -> str:
    events: list[list[str]] = []
    for shift in shifts:
        times = event_times(shift.work_date, shift.shift_type)
        if not times:
            continue
        start, end = times
        summary = (
            f"{shift.person.name} {shift.shift_type.name}" if multi_person else shift.shift_type.name
        )
        desc_parts = []
        if shift.note:
            desc_parts.append(shift.note)
        if multi_person:
            desc_parts.append(f"人员：{shift.person.name}（{shift.person.group_name or '默认组'}）")
        desc_parts.append(f"班次：{shift.shift_type.name}")
        events.append(
            build_event(
                uid=f"shift-{shift.id}@ics-roster",
                summary=summary,
                start=start,
                end=end,
                description="\n".join(desc_parts),
                color=shift.shift_type.color,
                stamp=shift.updated_at or shift.created_at,
            )
        )
    name = "团队排班" if multi_person else (shifts[0].person.name + " 排班" if shifts else "排班")
    return build_calendar(events, name)


@router.get("/team.ics", response_class=Response, response_model=None)
def team_feed(
    token: str = Query("", description="团队订阅 token"),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    x_feed_token: str = Header("", alias="X-Feed-Token"),
    db: Session = Depends(get_db),
):
    """整团队排班订阅地址，供日历客户端定期拉取。"""
    if token != TEAM_FEED_TOKEN and x_feed_token != TEAM_FEED_TOKEN:
        raise HTTPException(status_code=403, detail="订阅 token 无效")
    shifts = _load_shifts(db, date_from, date_to)
    body = _render(shifts, multi_person=True)
    return Response(content=body, media_type=ICS_MEDIA_TYPE)


@router.get("/person/{person_id}/{feed_token}.ics", response_class=Response, response_model=None)
def person_feed(
    person_id: int,
    feed_token: str,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    """单人订阅地址，token 泄露可立即轮换。"""
    person = db.get(Person, person_id)
    if not person or person.feed_token != feed_token:
        raise HTTPException(status_code=403, detail="订阅地址无效")
    shifts = _load_shifts(db, date_from, date_to, person_id, only_active=False)
    body = _render(shifts, multi_person=False)
    return Response(content=body, media_type=ICS_MEDIA_TYPE)
