import uuid

from flask import Blueprint, jsonify, request

from payments.service import PaymentError, start_payment
from storage.db import db
from storage.models import PaymentStatus

payments_bp = Blueprint("payments", __name__)


@payments_bp.post("")
def start_payment_route():
    # silent=True to avoid raising an error if the request body is not valid JSON.
    request_data = request.get_json(silent=True)

    if not request_data or not request_data.get("cart_id"):
        return jsonify({"error": "Request body is required and must contain a cart ID."}), 400

    try:
        cart_id = uuid.UUID(request_data["cart_id"])
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid cart ID."}), 400

    if request_data.get("payment_method_id"):
        try:
            payment_method_id = uuid.UUID(request_data["payment_method_id"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid payment method ID."}), 400
    else:
        payment_method_id = None

    try:
        payment = start_payment(
            db.session(),
            cart_id,
            payment_method_id,
        )

        body = {
            "id": str(payment.id),
            "cart_id": str(payment.cart_id),
            "status": payment.status,
            "amount": str(payment.amount),
            "currency": payment.currency,
        }

        if payment.status == PaymentStatus.SUCCEEDED:
            body["provider_charge_id"] = payment.provider_charge_id
            return jsonify(body), 201

        body["failure_reason"] = payment.failure_reason
        return jsonify(body), 402
    except PaymentError as error:
        return jsonify({"error": error.__class__.__name__}), error.status_code
