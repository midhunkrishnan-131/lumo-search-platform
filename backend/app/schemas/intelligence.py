"""Pydantic schemas for LUMO Phase 18: Universal Data Intelligence Engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportJobResponse(BaseModel):
    id: str
    source_kind: str
    format_type: str
    content_category: str
    file_name: str | None = None
    source_url: str | None = None
    file_size_bytes: int = 0
    content_hash: str | None = None
    status: str
    current_stage: str
    progress_pct: int = 0
    retry_count: int = 0
    error_message: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    workspace_item_id: str | None = None
    dataset_id: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class UrlImportRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)
    title: str | None = Field(default=None, max_length=500)
    collection_id: str | None = None
    classify_with_ai: bool = False
    provider: str = "auto"


class DocumentSummaryItem(BaseModel):
    id: str
    title: str
    source_type: str
    file_name: str | None = None
    file_type: str | None = None
    content_category: str = "general_document"
    summary: str | None = None
    word_count: int = 0
    created_at: datetime


class DocumentDetailResponse(DocumentSummaryItem):
    content: str
    source_url: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


DocumentAnalysisMode = Literal[
    "summarize",
    "explain",
    "qa",
    "key_info",
    "entities",
    "dates",
    "topics",
    "faq",
    "study_notes",
    "action_items",
    "report",
]


class DocumentAnalyzeRequest(BaseModel):
    mode: DocumentAnalysisMode = "summarize"
    question: str | None = Field(default=None, max_length=1500)
    provider: str = "auto"


class DocumentCompareRequest(BaseModel):
    document_ids: list[str] = Field(..., min_length=2, max_length=8)
    question: str | None = Field(default=None, max_length=1500)
    provider: str = "auto"


class CrossAnalysisRequest(BaseModel):
    source_ids: list[str] = Field(..., min_length=2, max_length=10)
    question: str | None = Field(default=None, max_length=1500)
    provider: str = "auto"


class ColumnProfile(BaseModel):
    name: str
    inferred_type: str
    non_null_count: int
    missing_count: int
    missing_pct: float
    unique_count: int
    sample_values: list[Any] = Field(default_factory=list)
    numeric_stats: dict[str, float] | None = None
    top_categories: list[dict[str, Any]] = Field(default_factory=list)
    date_range: dict[str, str] | None = None


class DatasetSummaryResponse(BaseModel):
    id: str
    workspace_item_id: str | None = None
    title: str
    file_name: str | None = None
    file_type: str
    row_count: int
    column_count: int
    sheet_count: int
    sheet_names: list[str] = Field(default_factory=list)
    active_sheet: str | None = None
    summary: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetDetailResponse(DatasetSummaryResponse):
    columns_json: list[dict[str, Any]] = Field(default_factory=list)
    profile_json: dict[str, Any] = Field(default_factory=dict)


class DatasetAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1500)
    provider: str = "auto"


ChartType = Literal["bar", "line", "pie", "histogram", "scatter"]


class DatasetVisualizeRequest(BaseModel):
    chart_type: ChartType | None = None
    x_column: str | None = None
    y_column: str | None = None
    limit: int = Field(default=20, ge=2, le=100)


class ChartSuggestion(BaseModel):
    chart_type: ChartType
    title: str
    x_column: str
    y_column: str | None = None
    reason: str


class VisualizationResponse(BaseModel):
    dataset_id: str
    chart_type: ChartType
    title: str
    x_label: str
    y_label: str
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    points: list[dict[str, float]] = Field(default_factory=list)
    suggestions: list[ChartSuggestion] = Field(default_factory=list)


class AnalysisReportResponse(BaseModel):
    id: str
    report_type: str
    title: str
    question: str | None = None
    summary: str
    result_json: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    provider: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
