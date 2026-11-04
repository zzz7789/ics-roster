"""首次启动时写入默认班次类型与管理员账号。"""

import logging
import secrets

from sqlalchemy import select

from .config import ADMIN_PASSWORD, ADMIN_USER
from .db import SessionLocal
from .models import ShiftType, User
from .services.auth import hash_password

log = logging.getLogger("ics-roster.seed")

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


def ensure_admin() -> None:
    """没有账号时创建管理员；未配置密码则随机生成并打印到日志。"""
    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)):
            return
        password = ADMIN_PASSWORD or secrets.token_urlsafe(9)
        db.add(
            User(
                username=ADMIN_USER,
                password_hash=hash_password(password),
                display_name="管理员",
                role="admin",
            )
        )
        db.commit()
        if ADMIN_PASSWORD:
            log.warning("已创建管理员账号 %s（密码来自 ICS_ROSTER_ADMIN_PASSWORD）", ADMIN_USER)
        else:
            log.warning(
                "已创建管理员账号 %s，初始密码：%s —— 请登录后立即修改", ADMIN_USER, password
            )
