"""请求/响应模型（pydantic v2）。"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str = "#4f8cff"
    group_name: str = ""
    active: bool = True


class PersonOut(PersonIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feed_token: str


class ShiftTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=32)
    start_time: str = "08:00"
    end_time: str = "16:00"
    ends_next_day: bool = False
    emit_to_calendar: bool = True
    color: str = "#4f8cff"


class ShiftTypeOut(ShiftTypeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ShiftIn(BaseModel):
    person_id: int
    shift_type_id: int
    work_date: date
    note: str = ""


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    shift_type_id: int
    work_date: date
    note: str
    updated_at: datetime | None = None


class ShiftBulkIn(BaseModel):
    """排班生成后整批上传：同人同天已存在则覆盖。"""

    items: list[ShiftIn]
