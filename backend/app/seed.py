"""首次启动时写入默认班次类型，避免空库无选项。"""

from sqlalchemy import select

from .db import SessionLocal
from .models import ShiftType

DEFAULT_TYPES = [
    dict(
        code="morning",
        name="早班",
        start_time="08:00",
        end_time="16:00",
        ends_next_day=False,
        emit_to_calendar=True,
        color="#f5a524",
    ),
    dict(
        code="evening",
        name="晚班",
        start_time="16:00",
        end_time="00:00",
        ends_next_day=True,
        emit_to_calendar=True,
        color="#7c5cff",
    ),
    dict(
        code="night",
        name="夜班",
        start_time="00:00",
        end_time="08:00",
        ends_next_day=False,
        emit_to_calendar=True,
        color="#3b4a6b",
    ),
    dict(
        code="rest",
        name="休息",
        start_time="",
        end_time="",
        ends_next_day=False,
        emit_to_calendar=False,
        color="#94a3b8",
    ),
]


def seed_defaults() -> None:
    with SessionLocal() as db:
        if db.scalar(select(ShiftType.id).limit(1)):
            return
        db.add_all(ShiftType(**item) for item in DEFAULT_TYPES)
        db.commit()
