from app.models.enums import SafetyAction
from app.services.input_safety import InputSafetyGuard


def test_personal_values_and_private_ip_are_redacted():
    decision = InputSafetyGuard().inspect(
        "联系 demo@example.com 或 13800138000，服务地址是 10.0.0.8"
    )

    assert decision.action == SafetyAction.REDACTED
    assert decision.safe_question is not None
    assert "demo@example.com" not in decision.safe_question
    assert "13800138000" not in decision.safe_question
    assert "10.0.0.8" not in decision.safe_question
    assert set(decision.detected_types) == {"email", "phone", "private_ip"}
