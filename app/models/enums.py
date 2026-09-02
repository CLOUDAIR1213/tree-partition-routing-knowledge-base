from enum import StrEnum


class Partition(StrEnum):
    FINANCE = "finance"
    HR = "hr"
    TECH = "tech"


class RouteName(StrEnum):
    FINANCE = "finance"
    HR = "hr"
    TECH = "tech"
    COMPOSITE = "composite"
    CLARIFY = "clarify"


class RouteKind(StrEnum):
    SINGLE = "single"
    COMPOSITE = "composite"
    CLARIFY = "clarify"


class DecisionSource(StrEnum):
    USER_HINT = "user_hint"
    LLM = "llm"
    SAFETY_FALLBACK = "safety_fallback"


class SafetyAction(StrEnum):
    SAFE = "safe"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class AnswerSource(StrEnum):
    INTERNAL = "internal"
    WEB = "web"
    NONE = "none"


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
