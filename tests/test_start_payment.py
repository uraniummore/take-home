import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

URL = "/payments"


def _post(client, payload):
    if payload is None:
        return client.post(URL)
    return client.post(URL, json=payload)


def test_missing_body_is_rejected(client):
    response = client.post(URL, data="{", content_type="application/json")

    assert response.status_code == 400
    assert response.get_json()["error"] == (
        "Request body is required and must contain a cart ID."
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "Request body is required and must contain a cart ID."),
        ({}, "Request body is required and must contain a cart ID."),
        ({"cart_id": "not-a-uuid"}, "Invalid cart ID."),
        (
            {"cart_id": str(uuid.uuid4()), "payment_method_id": "not-a-uuid"},
            "Invalid payment method ID.",
        ),
    ],
)
def test_bad_request_is_rejected(client, payload, message):
    response = _post(client, payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == message


def test_successful_payment_charges_the_snapshotted_price_and_checks_out(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("99.00"), stock=5)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=2, unit_price=Decimal("12.50"))
    card_id = shop.card(user_id, "tok_ok")

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
    )

    assert response.status_code == 201
    body = response.get_json()
    payment_id = uuid.UUID(body["id"])
    assert body["cart_id"] == str(cart_id)
    assert body["status"] == "succeeded"
    assert body["amount"] == "25.00"
    assert body["currency"].strip() == "USD"
    assert body["provider_charge_id"] == f"ch_{payment_id.hex}"

    assert shop.cart_status(cart_id) == "checked_out"
    saved = shop.payments(cart_id)
    assert len(saved) == 1
    assert saved[0].status == "succeeded"
    assert saved[0].created_at is not None
    assert saved[0].updated_at is not None
    assert shop.product_row(product_id) == (Decimal("99.00"), 5)


def test_omitted_card_uses_the_default(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    shop.card(user_id, "tok_other", default=False)
    default_card_id = shop.card(user_id, "tok_ok", default=True)

    response = client.post(URL, json={"cart_id": str(cart_id)})

    assert response.status_code == 201
    saved = shop.payments(cart_id)
    assert saved[0].payment_method_id == default_card_id


def test_declined_card_leaves_the_cart_active(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    card_id = shop.card(user_id, "tok_decline")

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
    )

    assert response.status_code == 402
    body = response.get_json()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "card_declined"
    assert "provider_charge_id" not in body
    assert shop.cart_status(cart_id) == "active"
    saved = shop.payments(cart_id)
    assert saved[0].status == "failed"
    assert saved[0].provider_charge_id is None


def test_declined_cart_can_be_paid_with_another_card(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    declined_card_id = shop.card(user_id, "tok_decline")
    good_card_id = shop.card(user_id, "tok_ok")

    declined = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(declined_card_id)},
    )
    paid = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(good_card_id)},
    )

    assert declined.status_code == 402
    assert paid.status_code == 201
    assert shop.cart_status(cart_id) == "checked_out"
    statuses = sorted(payment.status for payment in shop.payments(cart_id))
    assert statuses == ["failed", "succeeded"]


def test_unknown_cart_is_not_found(client, shop):
    missing_cart_id = uuid.uuid4()

    response = client.post(URL, json={"cart_id": str(missing_cart_id)})

    assert response.status_code == 404
    assert response.get_json()["error"] == "CartNotFoundError"
    assert shop.payments(missing_cart_id) == []


@pytest.mark.parametrize("status", ["checked_out", "abandoned"])
def test_inactive_cart_is_rejected(client, shop, status):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id, status=status)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    card_id = shop.card(user_id, "tok_ok")

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "CartNotActiveError"
    assert shop.cart_status(cart_id) == status
    assert shop.payments(cart_id) == []


def test_empty_cart_is_rejected(client, shop):
    user_id = shop.user()
    cart_id = shop.cart(user_id)
    card_id = shop.card(user_id, "tok_ok")

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "CartEmptyError"
    assert shop.payments(cart_id) == []


def test_unknown_card_is_not_found(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))

    response = client.post(
        URL,
        json={
            "cart_id": str(cart_id),
            "payment_method_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "PaymentMethodIdNotFoundError"
    assert shop.cart_status(cart_id) == "active"
    assert shop.payments(cart_id) == []


def test_another_users_card_is_rejected(client, shop):
    buyer_id = shop.user(name="Ada")
    owner_id = shop.user(name="Grace")
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(buyer_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    foreign_card_id = shop.card(owner_id, "tok_ok")

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(foreign_card_id)},
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "PaymentMethodNotOwnedError"
    assert shop.cart_status(cart_id) == "active"
    assert shop.payments(cart_id) == []


def test_missing_default_card_is_rejected(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    shop.card(user_id, "tok_ok", default=False)

    response = client.post(URL, json={"cart_id": str(cart_id)})

    assert response.status_code == 422
    assert response.get_json()["error"] == "NoDefaultPaymentMethodError"
    assert shop.payments(cart_id) == []


def test_zero_amount_is_not_reported_as_a_duplicate(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("0.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("0.00"))
    card_id = shop.card(user_id, "tok_ok")

    with pytest.raises(IntegrityError):
        client.post(
            URL,
            json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
        )

    assert shop.cart_status(cart_id) == "active"
    assert shop.payments(cart_id) == []


def test_pending_payment_blocks_a_second_charge(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    card_id = shop.card(user_id, "tok_ok")
    shop.pending_payment(cart_id, card_id, Decimal("10.00"))

    response = client.post(
        URL,
        json={"cart_id": str(cart_id), "payment_method_id": str(card_id)},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "PaymentAlreadyExistsError"
    assert shop.cart_status(cart_id) == "active"
    saved = shop.payments(cart_id)
    assert len(saved) == 1
    assert saved[0].status == "pending"


def test_paid_cart_cannot_be_charged_again(client, shop):
    user_id = shop.user()
    product_id = shop.product(price=Decimal("10.00"), stock=1)
    cart_id = shop.cart(user_id)
    shop.item(cart_id, product_id, quantity=1, unit_price=Decimal("10.00"))
    card_id = shop.card(user_id, "tok_ok")
    payload = {"cart_id": str(cart_id), "payment_method_id": str(card_id)}

    first = client.post(URL, json=payload)
    second = client.post(URL, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.get_json()["error"] == "CartNotActiveError"
    assert len(shop.payments(cart_id)) == 1
