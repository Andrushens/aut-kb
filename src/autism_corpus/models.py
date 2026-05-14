from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ContentType = Literal[
    "patient-info",
    "clinical-guideline",
    "research-article",
    "fact-sheet",
    "toolkit",
]

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceItemRef(_Frozen):
    source_id: str
    item_id: str
    url: str | None = None


class RawDocument(_Frozen):
    source_id: str
    source_item_id: str
    url: str
    content_type_header: str | None
    payload: bytes
    fetched_at: datetime


class ParsedDocument(_Frozen):
    source_id: str
    source_item_id: str
    canonical_url: str
    title: str
    text: str
    language: str
    published_at: date | None
    last_modified_at: date | None
    licence: str
    licence_url: str
    attribution: str
    content_type: ContentType
    medical_disclaimer_required: bool
    hash: str = Field(pattern=_HEX_64.pattern)
    fetched_at: datetime

    @property
    def document_id(self) -> str:
        return f"{self.source_id}::{self.source_item_id}"


class Chunk(_Frozen):
    chunk_id: str
    document_id: str
    source_id: str
    canonical_url: str
    title: str
    breadcrumb: str = Field(min_length=1)
    text: str
    token_count: int = Field(gt=0)
    language: str
    licence: str
    attribution: str
    content_type: ContentType
    medical_disclaimer_required: bool
    published_at: date | None = None
    fetched_at: datetime

    @model_validator(mode="after")
    def _chunk_id_under_document(self) -> Chunk:
        if not self.chunk_id.startswith(self.document_id + "::"):
            raise ValueError(
                f"chunk_id {self.chunk_id!r} must start with document_id {self.document_id!r}"
            )
        return self


class Manifest(_Frozen):
    run_id: str
    pipeline_version: str
    sources: dict[str, dict[str, int]]
    licences: dict[str, int]
    input_hash: str = Field(pattern=_HEX_64.pattern)
    generated_at: datetime

    @property
    def total_chunks(self) -> int:
        return sum(s.get("chunks", 0) for s in self.sources.values())

    @property
    def total_documents(self) -> int:
        return sum(s.get("documents", 0) for s in self.sources.values())
