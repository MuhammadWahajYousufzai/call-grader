"""Pydantic domain models for calls, segments, grades."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CallRecord(BaseModel):
    id: str = ""
    source: str = "jazz_business_line"
    source_call_id: str = ""
    dedupe_key: str = ""
    actual_started_at: str = ""
    reporting_date: str = ""
    direction: str = "UNKNOWN"
    raw_jazz_status: str = ""
    canonical_status: str = "UNKNOWN"
    caller_number: str = ""
    callee_number: str = ""
    raw_customer_number: str = ""
    normalized_customer_number: str = ""
    agent_id: str = ""
    agent_name_snapshot: str = ""
    jazz_agent_identifier: str = ""
    duration_seconds: int = 0
    recording_available: bool = False
    recording_storage_file_id: str = ""
    recording_sha256: str = ""
    recording_downloaded_at: str = ""
    recording_retention_due_at: str = ""
    recording_deleted_at: str = ""
    recording_delete_reason: str = ""
    pipeline_status: str = "DISCOVERED"
    retry_count: int = 0
    last_error_code: str = ""
    last_error_message: str = ""
    transcription_model: str = ""
    grader_model: str = ""
    grading_prompt_version: str = ""
    rubric_version: str = ""
    created_at: str = ""
    updated_at: str = ""


class TranscriptSegment(BaseModel):
    id: str = ""
    call_id: str = ""
    sequence: int = 0
    speaker_raw: str = ""
    speaker_role: Literal["Agent", "Customer", "Unknown"] = "Unknown"
    speaker_confidence: float = 0.0
    uncertain: bool = False
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    raw_text: str = ""
    roman_urdu_text: str = ""


class DimensionScore(BaseModel):
    score: float | None = None
    not_applicable: bool = False
    evidence: str = ""
    segment_ids: list[str] = Field(default_factory=list)


class Strength(BaseModel):
    category: str = ""
    segment_id: str = ""
    timestamp_seconds: float = 0.0
    evidence: str = ""
    explanation: str = ""


class Mistake(BaseModel):
    category: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    segment_id: str = ""
    timestamp_seconds: float = 0.0
    evidence: str = ""
    explanation: str = ""
    better_approach: str = ""
    example_response_roman_urdu: str = ""


class CoachingAction(BaseModel):
    priority: int = 1
    action: str = ""
    example_response_roman_urdu: str = ""


class CriticalFlag(BaseModel):
    flag: str = ""
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    segment_id: str = ""
    explanation: str = ""


class GradeResult(BaseModel):
    call_id: str = ""
    call_type: str = "other"
    primary_intent: str = "other"
    secondary_intents: list[str] = Field(default_factory=list)
    customer_requested_order: bool = False
    order_detected: bool = False
    complaint_detected: bool = False
    issue_detected: bool = False
    issue_resolved: bool = False
    follow_up_required: bool = False
    customer_sentiment_start: str = "neutral"
    customer_sentiment_end: str = "neutral"
    conversation_outcome: str = ""
    dimension_scores: dict[str, DimensionScore] = Field(default_factory=dict)
    overall_score: float = 0.0
    strengths: list[Strength] = Field(default_factory=list)
    mistakes: list[Mistake] = Field(default_factory=list)
    coaching_actions: list[CoachingAction] = Field(default_factory=list)
    critical_flags: list[CriticalFlag] = Field(default_factory=list)
    analysis: str = ""
    coaching_summary: str = ""
    needs_human_review: bool = False
    review_reason: str = ""
    grader_model: str = ""
    romanizer_model: str = ""
    grading_prompt_version: str = ""
    rubric_version: str = ""
    business_rules_version: str = ""
    order_details: dict[str, Any] = Field(default_factory=dict)
