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


# ----------------------------- ICS 导入 -----------------------------


class ImportGroup(BaseModel):
    """一份 ICS 里按「标题 + 时段」聚出的一组事件，供人工确认映射。"""

    key: str
    summary: str
    time_label: str
    all_day: bool
    count: int
    first_date: date
    last_date: date
    suggested_person_id: int | None = None
    suggested_person_name: str | None = None
    suggested_new_person_name: str = ""
    suggested_shift_type_id: int | None = None
    suggested_shift_type_name: str | None = None


class ImportPreviewOut(BaseModel):
    groups: list[ImportGroup]
    warnings: list[str] = []
    calendar_names: str = ""
    total_events: int = 0


class ImportApplyOut(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    warnings: list[str] = []


# ----------------------------- Excel 导入 -----------------------------


class ExcelPersonOut(BaseModel):
    name: str
    person_id: int | None = None
    counts: dict[str, int] = {}
    day_count: int = 0


class ExcelSheetOut(BaseModel):
    filename: str
    sheet_name: str
    title: str = ""
    year: int
    month: int
    date_matched: bool = True
    day_count: int = 0
    shift_labels: list[str] = []
    # 标签 -> 建议的班次类型 id（如 「早」-> 早班），识别不出则为 None
    label_suggestions: dict[str, int | None] = {}
    people: list[ExcelPersonOut] = []
    warnings: list[str] = []


class ExcelPreviewOut(BaseModel):
    sheets: list[ExcelSheetOut] = []
    warnings: list[str] = []


class ExcelApplyOut(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    persons_created: int = 0
    warnings: list[str] = []
