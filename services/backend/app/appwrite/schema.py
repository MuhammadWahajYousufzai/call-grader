"""Canonical Appwrite schema — single source of truth for bootstrap + repos.

Table IDs are deterministic across local and production.
"""

from __future__ import annotations

TABLES: dict[str, dict] = {
    "agents": {
        "name": "agents",
        "attributes": [
            {"key": "name", "type": "string", "size": 128, "required": True},
            {"key": "jazz_identifier", "type": "string", "size": 128, "required": False},
            {"key": "jazz_extension", "type": "string", "size": 64, "required": False},
            {"key": "active", "type": "boolean", "required": False, "default": True},
        ],
        "indexes": [
            {"key": "idx_jazz_identifier", "type": "key", "attributes": ["jazz_identifier"]},
        ],
    },
    "calls": {
        "name": "calls",
        "attributes": [
            {"key": "source", "type": "string", "size": 64, "required": True},
            {"key": "source_call_id", "type": "string", "size": 256, "required": False},
            {"key": "dedupe_key", "type": "string", "size": 128, "required": True},
            {"key": "actual_started_at", "type": "datetime", "required": False},
            {"key": "reporting_date", "type": "string", "size": 16, "required": False},
            {"key": "direction", "type": "string", "size": 16, "required": False},
            {"key": "raw_jazz_status", "type": "string", "size": 128, "required": False},
            {"key": "canonical_status", "type": "string", "size": 32, "required": False},
            {"key": "caller_number", "type": "string", "size": 64, "required": False},
            {"key": "callee_number", "type": "string", "size": 64, "required": False},
            {"key": "raw_customer_number", "type": "string", "size": 64, "required": False},
            {"key": "normalized_customer_number", "type": "string", "size": 64, "required": False},
            {"key": "agent_id", "type": "string", "size": 64, "required": False},
            {"key": "agent_name_snapshot", "type": "string", "size": 128, "required": False},
            {"key": "jazz_agent_identifier", "type": "string", "size": 128, "required": False},
            {"key": "duration_seconds", "type": "integer", "required": False},
            {"key": "recording_available", "type": "boolean", "required": False},
            {"key": "recording_storage_file_id", "type": "string", "size": 128, "required": False},
            {"key": "recording_sha256", "type": "string", "size": 128, "required": False},
            {"key": "recording_downloaded_at", "type": "datetime", "required": False},
            {"key": "recording_retention_due_at", "type": "datetime", "required": False},
            {"key": "recording_deleted_at", "type": "datetime", "required": False},
            {"key": "recording_delete_reason", "type": "string", "size": 256, "required": False},
            {"key": "pipeline_status", "type": "string", "size": 64, "required": False},
            {"key": "retry_count", "type": "integer", "required": False},
            {"key": "last_error_code", "type": "string", "size": 64, "required": False},
            {"key": "last_error_message", "type": "string", "size": 1024, "required": False},
            {"key": "transcription_model", "type": "string", "size": 128, "required": False},
            {"key": "grader_model", "type": "string", "size": 128, "required": False},
            {"key": "grading_prompt_version", "type": "string", "size": 32, "required": False},
            {"key": "rubric_version", "type": "string", "size": 32, "required": False},
            {"key": "raw_jazz_row", "type": "string", "size": 4096, "required": False},
        ],
        "indexes": [
            {"key": "uniq_dedupe", "type": "unique", "attributes": ["dedupe_key"]},
            {"key": "idx_reporting_date", "type": "key", "attributes": ["reporting_date"]},
            {"key": "idx_customer", "type": "key", "attributes": ["normalized_customer_number"]},
            {"key": "idx_agent", "type": "key", "attributes": ["agent_id"]},
            {"key": "idx_pipeline", "type": "key", "attributes": ["pipeline_status"]},
            {"key": "idx_started", "type": "key", "attributes": ["actual_started_at"]},
        ],
    },
    "transcript_segments": {
        "name": "transcript_segments",
        "attributes": [
            {"key": "call_id", "type": "string", "size": 64, "required": True},
            {"key": "sequence", "type": "integer", "required": True},
            {"key": "speaker_raw", "type": "string", "size": 64, "required": False},
            {"key": "speaker_role", "type": "string", "size": 32, "required": False},
            {"key": "speaker_confidence", "type": "float", "required": False},
            {"key": "uncertain", "type": "boolean", "required": False},
            {"key": "start_seconds", "type": "float", "required": False},
            {"key": "end_seconds", "type": "float", "required": False},
            {"key": "raw_text", "type": "string", "size": 4096, "required": False},
            {"key": "roman_urdu_text", "type": "string", "size": 4096, "required": False},
        ],
        "indexes": [
            {"key": "idx_call", "type": "key", "attributes": ["call_id"]},
            {"key": "idx_call_seq", "type": "key", "attributes": ["call_id", "sequence"]},
        ],
    },
    "call_grades": {
        "name": "call_grades",
        "attributes": [
            {"key": "call_id", "type": "string", "size": 64, "required": True},
            {"key": "overall_score", "type": "float", "required": False},
            {"key": "call_type", "type": "string", "size": 64, "required": False},
            {"key": "primary_intent", "type": "string", "size": 64, "required": False},
            {"key": "grader_model", "type": "string", "size": 128, "required": False},
            {"key": "grading_prompt_version", "type": "string", "size": 32, "required": False},
            {"key": "rubric_version", "type": "string", "size": 32, "required": False},
            {"key": "result_json", "type": "string", "size": 65536, "required": False},
            {"key": "human_reviewed", "type": "boolean", "required": False},
            {"key": "human_score", "type": "float", "required": False},
            {"key": "human_review_notes", "type": "string", "size": 4096, "required": False},
            {"key": "reviewed_by", "type": "string", "size": 128, "required": False},
            {"key": "reviewed_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {"key": "idx_grade_call", "type": "key", "attributes": ["call_id"]},
        ],
    },
    "processing_jobs": {
        "name": "processing_jobs",
        "attributes": [
            {"key": "job_type", "type": "string", "size": 32, "required": True},
            {"key": "call_id", "type": "string", "size": 64, "required": False},
            {"key": "reporting_date", "type": "string", "size": 16, "required": False},
            {"key": "status", "type": "string", "size": 16, "required": False},
            {"key": "attempt_count", "type": "integer", "required": False},
            {"key": "max_attempts", "type": "integer", "required": False},
            {"key": "next_attempt_at", "type": "datetime", "required": False},
            {"key": "locked_by", "type": "string", "size": 128, "required": False},
            {"key": "lock_expires_at", "type": "datetime", "required": False},
            {"key": "last_error", "type": "string", "size": 2048, "required": False},
        ],
        "indexes": [
            {"key": "idx_job_status", "type": "key", "attributes": ["status"]},
            {"key": "idx_job_call", "type": "key", "attributes": ["call_id"]},
            {"key": "idx_job_next", "type": "key", "attributes": ["status", "next_attempt_at"]},
        ],
    },
    "ingestion_runs": {
        "name": "ingestion_runs",
        "attributes": [
            {"key": "started_at", "type": "datetime", "required": False},
            {"key": "finished_at", "type": "datetime", "required": False},
            {"key": "status", "type": "string", "size": 32, "required": False},
            {"key": "window_start", "type": "datetime", "required": False},
            {"key": "window_end", "type": "datetime", "required": False},
            {"key": "calls_discovered", "type": "integer", "required": False},
            {"key": "recordings_downloaded", "type": "integer", "required": False},
            {"key": "error_code", "type": "string", "size": 64, "required": False},
            {"key": "error_message", "type": "string", "size": 2048, "required": False},
        ],
        "indexes": [
            {"key": "idx_run_started", "type": "key", "attributes": ["started_at"]},
        ],
    },
    "daily_reports": {
        "name": "daily_reports",
        "attributes": [
            {"key": "reporting_date", "type": "string", "size": 16, "required": True},
            {"key": "status", "type": "string", "size": 32, "required": False},
            {"key": "metrics_json", "type": "string", "size": 65536, "required": False},
            {"key": "coaching_summary", "type": "string", "size": 16384, "required": False},
        ],
        "indexes": [
            {"key": "uniq_report_date", "type": "unique", "attributes": ["reporting_date"]},
        ],
    },
    "business_rules": {
        "name": "business_rules",
        "attributes": [
            {"key": "key", "type": "string", "size": 128, "required": True},
            {"key": "value", "type": "string", "size": 16384, "required": False},
            {"key": "version", "type": "integer", "required": False},
            {"key": "updated_by", "type": "string", "size": 128, "required": False},
        ],
        "indexes": [
            {"key": "uniq_rule_key", "type": "unique", "attributes": ["key"]},
        ],
    },
    "app_settings": {
        "name": "app_settings",
        "attributes": [
            {"key": "key", "type": "string", "size": 128, "required": True},
            {"key": "value", "type": "string", "size": 8192, "required": False},
        ],
        "indexes": [
            {"key": "uniq_setting_key", "type": "unique", "attributes": ["key"]},
        ],
    },
    "audit_logs": {
        "name": "audit_logs",
        "attributes": [
            {"key": "actor", "type": "string", "size": 128, "required": False},
            {"key": "action", "type": "string", "size": 128, "required": False},
            {"key": "target", "type": "string", "size": 256, "required": False},
            {"key": "metadata", "type": "string", "size": 4096, "required": False},
        ],
        "indexes": [
            {"key": "idx_audit_action", "type": "key", "attributes": ["action"]},
        ],
    },
}

DEFAULT_BUSINESS_RULES = [
    {"key": "products", "value": "Super Kernel Basmati, 1121 Kainat Steam/Sella, IRRI-6 (common/mota chawal). Bag sizes: 5kg, 10kg, 20kg, 50kg sack. Update prices via Settings; grader must not invent prices."},
    {"key": "delivery_policy", "value": "Standard Karachi delivery next working day unless confirmed otherwise. Out-of-city timelines must be confirmed, never guessed."},
    {"key": "returns_policy", "value": "Damaged/wrong-item complaints: apologize, record order details, promise callback/replacement per manager approval, always give a clear next step and follow-up time."},
    {"key": "discount_policy", "value": "Agents may not promise discounts above Rs 100/bag or free delivery without manager approval."},
    {"key": "order_requirements", "value": "Confirm: product/variety, quantity, delivery address/area, phone number, price if discussed, delivery expectation, and read back the order before closing."},
]

DEFAULT_SETTINGS = [
    {"key": "last_successful_sync", "value": ""},
    {"key": "last_successful_login", "value": ""},
    {"key": "business_rules_version", "value": "1"},
]
