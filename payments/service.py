from decimal import Decimal
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from payments.provider_mock import charge
from storage.models import Cart, CartStatus, Payment, PaymentStatus, UserPaymentMethod


class PaymentError(Exception):
    pass


class CartNotFoundError(PaymentError):
    status_code = 404


class CartNotActiveError(PaymentError):
    status_code = 409


class CartEmptyError(PaymentError):
    status_code = 422


class PaymentMethodIdNotFoundError(PaymentError):
    status_code = 404


class PaymentMethodNotOwnedError(PaymentError):
    status_code = 403


class NoDefaultPaymentMethodError(PaymentError):
    status_code = 422


class PaymentAlreadyExistsError(PaymentError):
    status_code = 409


def start_payment(
    session: Session,
    cart_id: uuid.UUID,
    payment_method_id: uuid.UUID | None,
) -> Payment:
    try:
        with session.begin():
            cart_stmt = (
                select(Cart)
                .where(Cart.id == cart_id)
                .with_for_update()
            )

            cart = session.execute(cart_stmt).scalar_one_or_none()

            if cart is None:
                raise CartNotFoundError()

            if cart.status != CartStatus.ACTIVE:
                raise CartNotActiveError()

            if not cart.items:
                raise CartEmptyError()

            if payment_method_id is not None:
                payment_method = session.get(
                    UserPaymentMethod, payment_method_id)

                if payment_method is None:
                    raise PaymentMethodIdNotFoundError()

                if payment_method.user_id != cart.user_id:
                    raise PaymentMethodNotOwnedError()
            else:
                payment_method_stmt = (
                    select(UserPaymentMethod)
                    .where(UserPaymentMethod.user_id == cart.user_id)
                    .where(UserPaymentMethod.is_default.is_(True))
                    .limit(1)
                )

                payment_method = session.execute(
                    payment_method_stmt).scalars().first()

                if payment_method is None:
                    raise NoDefaultPaymentMethodError()

            amount = sum(
                (item.quantity * item.unit_price for item in cart.items), Decimal("0"))

            payment = Payment(
                cart_id=cart.id,
                payment_method_id=payment_method.id,
                amount=amount,
                currency="USD",
                status=PaymentStatus.PENDING,
            )

            session.add(payment)
            session.flush()  # Trigger the insert.

            provider_token = payment_method.provider_token
            amount = payment.amount
            payment_id = payment.id
            currency = payment.currency
    except IntegrityError as e:
        raise PaymentAlreadyExistsError from e

    charge_result = charge(provider_token, amount, currency, payment_id)

    with session.begin():
        payment = session.get(Payment, payment_id)
        cart = session.get(Cart, cart_id)

        if charge_result.succeeded:
            payment.status = PaymentStatus.SUCCEEDED
            payment.provider_charge_id = charge_result.charge_id
            cart.status = CartStatus.CHECKED_OUT
        else:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = charge_result.failure_reason

    return payment
