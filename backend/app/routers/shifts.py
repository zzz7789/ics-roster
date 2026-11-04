"""人员与排班的基础 CRUD。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import Person, Shift, ShiftType
from ..schemas import (
    PersonIn,
    PersonOut,
    ShiftBulkIn,
    ShiftIn,
    ShiftOut,
    ShiftTypeIn,
    ShiftTypeOut,
)

router = APIRouter(prefix="/api", tags=["roster"])


# ----------------------------- 人员 -----------------------------


@router.get("/persons", response_model=list[PersonOut])
def list_persons(include_inactive: bool = False, db: Session = Depends(get_db)):
    stmt = select(Person).order_by(Person.group_name, Person.id)
    if not include_inactive:
        stmt = stmt.where(Person.active.is_(True))
    return db.scalars(stmt).all()


@router.post("/persons", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(payload: PersonIn, db: Session = Depends(get_db)):
    person = Person(**payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.put("/persons/{person_id}", response_model=PersonOut)
def update_person(person_id: int, payload: PersonIn, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    for key, value in payload.model_dump().items():
        setattr(person, key, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    # 保留历史：只停用，不物理删除
    person.active = False
    db.commit()


@router.post("/persons/{person_id}/token", response_model=PersonOut)
def rotate_token(person_id: int, db: Session = Depends(get_db)):
    """轮换订阅 token，旧订阅地址立即失效。"""
    from ..models import new_feed_token

    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="人员不存在")
    person.feed_token = new_feed_token()
    db.commit()
    db.refresh(person)
    return person


# ----------------------------- 班次类型 -----------------------------


@router.get("/shift-types", response_model=list[ShiftTypeOut])
def list_shift_types(db: Session = Depends(get_db)):
    return db.scalars(select(ShiftType).order_by(ShiftType.id)).all()


@router.post("/shift-types", response_model=ShiftTypeOut, status_code=status.HTTP_201_CREATED)
def create_shift_type(payload: ShiftTypeIn, db: Session = Depends(get_db)):
    row = ShiftType(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ----------------------------- 排班 -----------------------------


@router.get("/shifts", response_model=list[ShiftOut])
def list_shifts(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    person_id: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Shift).options(joinedload(Shift.shift_type)).order_by(Shift.work_date)
    if date_from:
        stmt = stmt.where(Shift.work_date >= date_from)
    if date_to:
        stmt = stmt.where(Shift.work_date <= date_to)
    if person_id:
        stmt = stmt.where(Shift.person_id == person_id)
    return db.scalars(stmt).all()


def _upsert(db: Session, item: ShiftIn) -> Shift:
    if not db.get(Person, item.person_id):
        raise HTTPException(status_code=404, detail=f"人员 {item.person_id} 不存在")
    if not db.get(ShiftType, item.shift_type_id):
        raise HTTPException(status_code=404, detail=f"班次类型 {item.shift_type_id} 不存在")
    existing = db.scalar(
        select(Shift).where(
            Shift.person_id == item.person_id, Shift.work_date == item.work_date
        )
    )
    if existing:
        existing.shift_type_id = item.shift_type_id
        existing.note = item.note
        return existing
    row = Shift(**item.model_dump())
    db.add(row)
    return row


@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def create_shift(payload: ShiftIn, db: Session = Depends(get_db)):
    row = _upsert(db, payload)
    db.commit()
    db.refresh(row)
    return row


@router.post("/shifts/bulk", response_model=list[ShiftOut])
def bulk_upsert(payload: ShiftBulkIn, db: Session = Depends(get_db)):
    """排班生成后整批上传，同人同天覆盖。返回本次落库结果。"""
    rows = [_upsert(db, item) for item in payload.items]
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


@router.put("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: int, payload: ShiftIn, db: Session = Depends(get_db)):
    row = db.get(Shift, shift_id)
    if not row:
        raise HTTPException(status_code=404, detail="排班记录不存在")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/shifts/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(shift_id: int, db: Session = Depends(get_db)):
    row = db.get(Shift, shift_id)
    if not row:
        raise HTTPException(status_code=404, detail="排班记录不存在")
    db.delete(row)
    db.commit()
