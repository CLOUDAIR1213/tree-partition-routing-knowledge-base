import ipaddress
import re

from app.models.enums import SafetyAction
from app.models.schemas import SafetyDecision


class InputSafetyGuard:
    _blocked_patterns = (
        ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)),
        ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{16,}", re.IGNORECASE)),
        ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE)),
        (
            "jwt",
            re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        ),
        (
            "password",
            re.compile(
                r"\b(?:password|passwd|pwd|db_password)\s*[:=]\s*[^\s,;]+",
                re.IGNORECASE,
            ),
        ),
    )
    _email = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?!\w)")
    _phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    _ipv4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")

    def inspect(self, question: str) -> SafetyDecision:
        detected = [name for name, pattern in self._blocked_patterns if pattern.search(question)]
        if detected:
            return SafetyDecision(
                action=SafetyAction.BLOCKED,
                safe_question=None,
                detected_types=detected,
                message="问题包含不应发送给模型或检索服务的秘密值",
            )

        safe_question = question
        redacted_types: list[str] = []
        safe_question, email_count = self._email.subn("[EMAIL]", safe_question)
        if email_count:
            redacted_types.append("email")
        safe_question, phone_count = self._phone.subn("[PHONE]", safe_question)
        if phone_count:
            redacted_types.append("phone")
        safe_question = self._redact_private_ips(safe_question, redacted_types)

        return SafetyDecision(
            action=(SafetyAction.REDACTED if redacted_types else SafetyAction.SAFE),
            safe_question=safe_question,
            detected_types=redacted_types,
        )

    def _redact_private_ips(self, question: str, detected: list[str]) -> str:
        found_private = False

        def replace(match: re.Match[str]) -> str:
            nonlocal found_private
            try:
                address = ipaddress.ip_address(match.group(0))
            except ValueError:
                return match.group(0)
            if address.is_private:
                found_private = True
                return "[PRIVATE_IP]"
            return match.group(0)

        result = self._ipv4.sub(replace, question)
        if found_private:
            detected.append("private_ip")
        return result

