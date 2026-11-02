from flask import Blueprint

payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/")
def payments_page():
    return "<h1>Payments</h1>"
