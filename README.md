# A take-home task for Solid Software.

This is the documentation for the take-home project I have built for Solid Software. The details of the task are described in [TASK.md](TASK.md), and partially - in [quickstart.sql](quickstart.sql) file's comments.

The summary of this task is to create an endpoint that starts the payment process for an online shopping cart.

## How to run this project.

For reliability, as well as simplicity, this project is fully containerised, and runs inside [Docker Compose](https://docs.docker.com/compose/). Docker is running without using the detached mode in order to keep the logs visible for testing transparency.


There are three commands that are necessary to launch and test this app.

To create a default env file:
```bash
cp .example.env .env
```

To build and launch the app:
```bash
docker compose up --build
```

And then to run the tests, open a second terminal and run:
```bash
docker compose run --rm app pytest
```

### Resetting the database

If you wish to empty the database and start anew, or make changes to `quickstart.sql`, this command deletes all volumes:

```bash
docker compose down -v
```

After running it, just rerun the launch command, and it's good to go.

## The endpoint

`POST /payments` creates a payment for a cart and charges the card.

```http
POST /payments
Content-Type: application/json

{ "cart_id": "<uuid>", "payment_method_id": "<uuid, optional>" }
```

`cart_id` is required. `payment_method_id` is optional. When it is omitted, the cart owner's default card is charged.

A successful charge returns `201` and the payment. `amount` is a decimal string. `provider_charge_id` is `ch_` plus the payment id, without hyphens.

```json
{
  "id": "a6ed81d8-2811-455c-914f-57ff14d9398e",
  "cart_id": "c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1",
  "status": "succeeded",
  "amount": "70.00",
  "currency": "USD",
  "provider_charge_id": "ch_a6ed81d82811455c914f57ff14d9398e"
}
```

A declined card returns `402`. The payment is saved as `failed`, and the cart stays `active`, so the same cart can be charged again with another card.

```json
{
  "id": "b7ce92e9-3922-466d-a250-68aa25e04a9f",
  "cart_id": "c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1",
  "status": "failed",
  "amount": "70.00",
  "currency": "USD",
  "failure_reason": "card_declined"
}
```

Every other failure returns a JSON object with one field, `error`, whose value is the exception name.

| Status | `error` | When |
|---|---|---|
| 400 | — | The body is missing, or an id is not a UUID. The response text explains which. |
| 403 | `PaymentMethodNotOwnedError` | The card belongs to another user. |
| 404 | `CartNotFoundError` | No cart has that id. |
| 404 | `PaymentMethodIdNotFoundError` | No card has that id. |
| 409 | `CartNotActiveError` | The cart is `checked_out` or `abandoned`. |
| 409 | `PaymentAlreadyExistsError` | A `pending` or `succeeded` payment already exists for the cart. |
| 422 | `CartEmptyError` | The cart has no items. |
| 422 | `NoDefaultPaymentMethodError` | No card was sent, and the user has no default card. |
| 500 | — | Anything else, including a cart whose total is `0.00`. |

Alice's cart from `quickstart.sql` is a working request. Her card token does not contain `decline`, so the first call returns `201`. A second call for the same cart returns `409`, because the cart is then `checked_out`.

```bash
curl -s -D- -X POST localhost:5000/payments \
  -H 'Content-Type: application/json' \
  -d '{"cart_id":"c1c1c1c1-c1c1-c1c1-c1c1-c1c1c1c1c1c1","payment_method_id":"11111111-2222-3333-4444-555555555555"}'
```

## Decisions I made, and notes I have taken.

I have kept an extensive log of what I was thinking about when I 
worked on this task, and I committed them into the [Thinking 
Logs](thinking-logs.md) file. This is the more concise version 
of them.

- There is no authentication. The cart's owner is the user who is charged, so the request has no `user_id`. `cart_id` is required. `payment_method_id` is optional, and when it is omitted the user's default card is used. The schema allows more than one default, so the first one is taken.
- The total is the sum of `quantity * unit_price` on the cart items, using `Decimal`. The task says a service already calculates the total, and no such service was provided. The current product price is not read, so a later price change does not change the charge. Stock is not reduced.
- The charge is in USD. Cart items do not store a currency, and every product in the base schema is USD. A cart that mixed currencies would be rejected when items are added, which this endpoint does not do.
- `amount` is `NUMERIC(12, 2)`, the same as the price columns in the base schema. A total above 9,999,999,999.99 cannot be stored. Card networks cap a charge far below that.
- A payment row is saved as `pending` before the provider is called, and the payment's id is the idempotency key. A cart can have many failed payments, and at most one that is `pending` or `succeeded`. A declined card leaves the cart `active`, so the customer can retry with another card.
- The provider is a mock. A token containing `decline` is declined with `card_declined`. Any other token succeeds, and the charge id is `ch_` plus the payment id. A provider that never answers is out of scope: the payment would stay `pending`. Refunds, 3-D Secure, and partial captures are out of scope too.
- A cart whose total is `0.00` fails the database check on `amount`. That is a constraint failure, not a duplicate payment, so the response is 500.
