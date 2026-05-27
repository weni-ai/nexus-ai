"""Bedrock per-document ingestion status constants."""

STRATEGY_JOB = "job"
STRATEGY_DIRECT = "direct"
STRATEGY_DIRECT_WITH_FALLBACK = "direct_with_fallback"

PATH_JOB = "job"
PATH_DIRECT = "direct"
PATH_JOB_FALLBACK = "job_fallback"

SUCCESS_STATUSES = frozenset({"INDEXED"})
FAILURE_STATUSES = frozenset({"FAILED", "IGNORED", "NOT_FOUND"})
PARTIAL_STATUSES = frozenset({"PARTIALLY_INDEXED", "METADATA_PARTIALLY_INDEXED"})

TRANSIENT_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "ServiceQuotaExceededException",
        "InternalServerException",
    }
)

NON_RETRYABLE_ERROR_CODES = frozenset({"AccessDeniedException"})
