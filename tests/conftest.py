import os
import uuid
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from flask.testing import FlaskClient
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import create_app
from storage.db import db
from storage.models import Cart, Payment, PaymentStatus

ROOT = Path(__file__).resolve().parents[1]


def _prepare_database() -> None:
    test_url = make_url(os.environ["TEST_DATABASE_URL"])
    admin_url = make_url(os.environ["DATABASE_URL"])

    with psycopg.connect(
        admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(test_url.database)
            )
        )
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_url.database))
        )

    with psycopg.connect(
        test_url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        script = (ROOT / "quickstart.sql").read_text()
        for statement in script.split(";"):
            if statement.strip():
                connection.execute(statement)

    alembic_config = Config(str(ROOT / "alembic.ini"))
    alembic_config.set_main_option(
        "sqlalchemy.url",
        test_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    command.upgrade(alembic_config, "head")


@pytest.fixture(scope="session")
def app():
    _prepare_database()
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": os.environ["TEST_DATABASE_URL"],
        }
    )
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app) -> FlaskClient:
    return app.test_client()


class Shop:
    """Insert rows with SQL, database defaults fill the timestamp columns."""

    def __init__(self, app) -> None:
        self.app = app

    def user(self, name: str = "Ada") -> uuid.UUID:
        user_id = uuid.uuid4()

        def insert(session: Session) -> uuid.UUID:
            session.execute(
                text(
                    "INSERT INTO users (id, email, name) VALUES (:id, :email, :name)"
                ),
                {"id": user_id, "email": f"{user_id}@example.com", "name": name},
            )
            return user_id

        return self._commit(insert)

    def product(
        self, price: Decimal, stock: int, name: str = "Mug"
    ) -> uuid.UUID:
        product_id = uuid.uuid4()

        def insert(session: Session) -> uuid.UUID:
            session.execute(
                text(
                    """
                    INSERT INTO products (id, name, price, currency, stock_quantity)
                    VALUES (:id, :name, :price, 'USD', :stock)
                    """
                ),
                {"id": product_id, "name": name, "price": price, "stock": stock},
            )
            return product_id

        return self._commit(insert)

    def cart(self, user_id: uuid.UUID, status: str = "active") -> uuid.UUID:
        cart_id = uuid.uuid4()

        def insert(session: Session) -> uuid.UUID:
            session.execute(
                text(
                    """
                    INSERT INTO carts (id, user_id, status)
                    VALUES (:id, :user_id, :status)
                    """
                ),
                {"id": cart_id, "user_id": user_id, "status": status},
            )
            return cart_id

        return self._commit(insert)

    def item(
        self,
        cart_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity: int,
        unit_price: Decimal,
    ) -> uuid.UUID:
        item_id = uuid.uuid4()

        def insert(session: Session) -> uuid.UUID:
            session.execute(
                text(
                    """
                    INSERT INTO cart_items (id, cart_id, product_id, quantity, unit_price)
                    VALUES (:id, :cart_id, :product_id, :quantity, :unit_price)
                    """
                ),
                {
                    "id": item_id,
                    "cart_id": cart_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                },
            )
            return item_id

        return self._commit(insert)

    def card(
        self, user_id: uuid.UUID, token: str, *, default: bool = False
    ) -> uuid.UUID:
        card_id = uuid.uuid4()

        def insert(session: Session) -> uuid.UUID:
            session.execute(
                text(
                    """
                    INSERT INTO user_payment_methods
                        (id, user_id, provider_token, is_default)
                    VALUES (:id, :user_id, :token, :is_default)
                    """
                ),
                {
                    "id": card_id,
                    "user_id": user_id,
                    "token": token,
                    "is_default": default,
                },
            )
            return card_id

        return self._commit(insert)

    def pending_payment(
        self, cart_id: uuid.UUID, card_id: uuid.UUID, amount: Decimal
    ) -> uuid.UUID:
        def insert(session: Session) -> uuid.UUID:
            payment = Payment(
                cart_id=cart_id,
                payment_method_id=card_id,
                amount=amount,
                currency="USD",
                status=PaymentStatus.PENDING,
            )
            session.add(payment)
            session.flush()
            return payment.id

        return self._commit(insert)

    def cart_status(self, cart_id: uuid.UUID) -> str:
        def read(session: Session) -> str:
            return session.get(Cart, cart_id).status

        return self._read(read)

    def payments(self, cart_id: uuid.UUID) -> list[Payment]:
        def read(session: Session) -> list[Payment]:
            rows = list(
                session.scalars(select(Payment).where(Payment.cart_id == cart_id))
            )
            session.expunge_all()
            return rows

        return self._read(read)

    def product_row(self, product_id: uuid.UUID) -> tuple[Decimal, int]:
        def read(session: Session) -> tuple[Decimal, int]:
            row = session.execute(
                text(
                    "SELECT price, stock_quantity FROM products WHERE id = :id"
                ),
                {"id": product_id},
            ).one()
            return row.price, row.stock_quantity

        return self._read(read)

    def _commit[T](self, work: Callable[[Session], T]) -> T:
        with self.app.app_context():
            result = work(db.session)
            db.session.commit()
            db.session.remove()
            return result

    def _read[T](self, work: Callable[[Session], T]) -> T:
        with self.app.app_context():
            result = work(db.session)
            db.session.remove()
            return result


@pytest.fixture
def shop(app) -> Shop:
    with app.app_context():
        db.session.execute(
            text(
                """
                TRUNCATE payments, cart_items, carts,
                         user_payment_methods, products, users
                RESTART IDENTITY CASCADE
                """
            )
        )
        db.session.commit()
        db.session.remove()
    return Shop(app)
