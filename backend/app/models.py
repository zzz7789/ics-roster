"""ORM 模型：人员、排班班次、班次类型字典。"""

import secrets
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_feed_token() -> str:
    return secrets.token_urlsafe(18)


class Person(Base):
    """参与排班的人员。每人一个只读订阅 token，便于手机日历单独订阅。"""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    # 前端日历着色用，形如 #4f8cff
    color: Mapped[str] = mapped_column(String(16), default="#4f8cff")
    # 所属小组，便于多人分组展示，暂不做强校验
    group_name: Mapped[str] = mapped_column(String(64), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    feed_token: Mapped[str] = mapped_column(String(64), unique=True, default=new_feed_token)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    shifts: Mapped[list["Shift"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class ShiftType(Base):
    """班次类型，如早班/晚班/休息；时间与是否写入日历均可配置。"""

    __tablename__ = "shift_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(32))
    start_time: Mapped[str] = mapped_column(String(5), default="")  # "08:00"
    end_time: Mapped[str] = mapped_column(String(5), default="")  # "16:00"
    # 结束时间是否落在次日（夜班）
    ends_next_day: Mapped[bool] = mapped_column(Boolean, default=False)
    # 休息类班次默认不写入日历
    emit_to_calendar: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[str] = mapped_column(String(16), default="#4f8cff")


class Shift(Base):
    """一条排班记录：某人在某天上了某个班。"""

    __tablename__ = "shift"
    __table_args__ = (UniqueConstraint("person_id", "work_date", name="uq_shift_person_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    shift_type_id: Mapped[int] = mapped_column(ForeignKey("shift_type.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    person: Mapped[Person] = relationship(back_populates="shifts")
    shift_type: Mapped[ShiftType] = relationship()


class User(Base):
    """登录账号。role 预留：admin 可管理一切，viewer 只读（当前均按 admin 处理）。"""

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="admin")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
