from enum import StrEnum


class Partition(StrEnum):
    FINANCE = "finance"
    HR = "hr"
    TECH = "tech"


class RouteName(StrEnum):
    FINANCE = "finance"
    HR = "hr"
    TECH = "tech"
    CLARIFY = "clarify"


class DecisionSource(StrEnum):
    USER_HINT = "user_hint"
    LLM = "llm"
    SAFETY_FALLBACK = "safety_fallback"


class SafetyAction(StrEnum):
    SAFE = "safe"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PENDING_REVIEW = "pending_review"
    INDEXING = "indexing"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
