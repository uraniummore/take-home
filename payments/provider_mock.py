from dataclasses import dataclass
from decimal import Decimal
import uuid


@dataclass(frozen=True)
class ChargeResult:
    succeeded: bool
    charge_id: str | None = None
    failure_reason: str | None = None

# No need to use amount or curreny, they're here to document the same arguments as a real provider.
def charge(token: str, amount: Decimal, currency: str, idempotency_key: uuid.UUID) -> ChargeResult:
    if "decline" in token:
        return ChargeResult(succeeded=False, failure_reason="card_declined")
    return ChargeResult(succeeded=True, charge_id=f"ch_{idempotency_key.hex}")
