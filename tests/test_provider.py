import uuid
from decimal import Decimal

from payments.provider_mock import charge


def test_successful_charge_uses_the_idempotency_key_as_the_charge_id():
    key = uuid.uuid4()

    result = charge("tok_ok", Decimal("10.00"), "USD", key)

    assert result.succeeded is True
    assert result.charge_id == f"ch_{key.hex}"
    assert result.failure_reason is None


def test_token_containing_decline_is_declined():
    result = charge("tok_decline", Decimal("10.00"), "USD", uuid.uuid4())

    assert result.succeeded is False
    assert result.charge_id is None
    assert result.failure_reason == "card_declined"
