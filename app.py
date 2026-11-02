import os
from typing import Any, Mapping

from flask import Flask

from storage.db import db


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]

    if config:
        app.config.update(config)

    db.init_app(app)

    from payments.routes import payments_bp
    app.register_blueprint(payments_bp, url_prefix="/payments")

    return app
