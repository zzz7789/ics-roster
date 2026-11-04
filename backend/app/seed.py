"""首次启动时写入默认班次类型与管理员账号。"""

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ADMIN_PASSWORD, ADMIN_USER
from .db import SessionLocal
from .models import ShiftType, User
from .services.auth import hash_password

log = logging.getLogger("ics-roster.seed")

DEFAULT_TYPES = [
    dict(
        code="morning",
        name="早班",
        start_time="09:00",
        end_time="17:00",
        ends_next_day=False,
        emit_to_calendar=True,
        color="#f5a524",
    ),
    dict(
        code="evening",
        name="晚班",
        start_time="17:00",
        end_time="00:00",
        ends_next_day=True,  # 跨天到次日 00:00
        emit_to_calendar=True,
        color="#7c5cff",
    ),
    dict(
        code="rest",
        name="休息",
        start_time="",
        end_time="",
        ends_next_day=False,
        emit_to_calendar=True,  # 休息按全天事件写入日历
        color="#94a3b8",
    ),
]


def seed_defaults() -> None:
    with SessionLocal() as db:
        if db.scalar(select(ShiftType.id).limit(1)):
            _ensure_rest_emitted(db)
            return
        db.add_all(ShiftType(**item) for item in DEFAULT_TYPES)
        db.commit()


def _ensure_rest_emitted(db: Session) -> None:
    """老库里的「休息」原先不写日历，这里统一改为写入（全天事件）。"""
    rest = db.scalar(select(ShiftType).where(ShiftType.code == "rest"))
    if rest is not None and not rest.emit_to_calendar:
        rest.emit_to_calendar = True
        db.commit()
        log.warning("休息班次已改为写入日历（全天事件）")


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
