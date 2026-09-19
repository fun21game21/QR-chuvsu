"""Server-owned building catalogue. Session coordinates are snapshots, never client input."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Campus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    name: str
    address: str
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    source_url: str
    google_maps_url: str
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} — {self.address}"


CATALOGUE = tuple(
    Campus.model_validate(row)
    for row in json.loads((Path(__file__).parents[1] / "campuses.json").read_text(encoding="utf-8"))
)
CAMPUSES = {campus.id: campus for campus in CATALOGUE}
if len(CAMPUSES) != len(CATALOGUE):
    raise RuntimeError("Duplicate campus identifiers")
