from pydantic import BaseModel
from typing import Optional


class PageCreate(BaseModel):
    url: str
    label: str = ""
    window_start: str  # ISO datetime
    window_end: str    # ISO datetime


class PageOut(BaseModel):
    id: int
    url: str
    label: str
    window_start: str
    window_end: str
    status: str
    last_error: Optional[str]
    attempts: int
    created_at: str
    updated_at: str
