import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.campuses import CAMPUSES


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


class CleanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def clean_strings(cls, value):
        if isinstance(value, str):
            value = " ".join(unicodedata.normalize("NFKC", value).split())
            if any(unicodedata.category(char) in {"Cc", "Cs", "Cf"} for char in value):
                raise ValueError("Управляющие и невидимые символы недопустимы")
            return value
        return value


class Student(CleanModel):
    student_name: str = Field(min_length=3, max_length=160)
    group_name: str = Field(min_length=1, max_length=80)


class SessionCreate(CleanModel):
    title: str = Field(min_length=1, max_length=160)
    group_name: str = Field(min_length=1, max_length=80)
    teacher_name: str = Field(min_length=1, max_length=160)
    campus_id: str = Field(min_length=1, max_length=40)
    duration_minutes: int = Field(default=30, ge=1, le=720)
    radius: int = Field(default=150, ge=10, le=5000)

    @field_validator("campus_id")
    @classmethod
    def known_campus(cls, value: str) -> str:
        if value not in CAMPUSES:
            raise ValueError("Выберите корпус ЧГУ из списка")
        return value


class BrowserFingerprint(CleanModel):
    user_agent: str = Field(min_length=1, max_length=512)
    language: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=100)
    screen_width: int = Field(ge=1, le=20000)
    screen_height: int = Field(ge=1, le=20000)


class AttendanceCreate(Student):
    # Missing geolocation is a business rejection recorded in the journal.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    fingerprint: BrowserFingerprint | None = None


class CodeInput(CleanModel):
    code: str

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        if not re.fullmatch(r"[0-9]{6}", value):
            raise ValueError("Введите шестизначный код")
        return value
