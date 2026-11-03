# Logging thoughts here.

Right. First things first - I have an empty folder, which I have to turn into a Flask project with SQLAlchemy. The task is described in [TASK.md](TASK.md), and some of the context is also present in the commented part of the `quickstart.sql` file.

## My actual thoughts here.

The task says "use your best judgement" for any missing context. Therefore, there are some assumptions I will make. I want to be able to retrace my thoughts, as well as allow the reviewer to do the same.

1. The **task** itself doesn't say this out loud, but the first thing I noticed is the word "migration", so I shall assume this means that I must add **Alembic** to my scope.

    > -- Run this file on an empty database before you start the task.
    <br> ... <br>
    -- This file does not define the payments table.
    <br>-- You design that part yourself. Add it as a new migration.

    **Assumption**: The author likely wants me to first create the DB, and then migrate a new table for the payment.

2. In this task, I will not necessarily use all the tables from `quickstart.sql`. Therefore, to keep it simple, I won't be mapping all of them to Alchemy models. This, in turn, means that when I do map the ones I need, Alembic's autogenerate will propse a drop_table for the tables that exist in the database, but not in my models.

    **Decision**: I will write the `payments` migration by hand.

3. Due to me not mapping out all tables from the quickstart file, `db.create_all()` during the test suite would build tables from my partial models, and miss the CHECK constraints and defaults.

    **Decision**: I will not use `create_all` at all. Instead of that, I shall build the test database the same way as the real one:

    - Load quickstart.sql into it.
    - Run alembic migrations.
    - Run tests against the schema we actually have.

4. I had this concern about following best practices: what's more optimal - mapping only the models I need, and using the approaches I described above, or mapping them all and creating some that I won't use, and running `create_all`? After some research, I came to these **conclusions**:

    - Mapping all models would lead me to keep the schema in two places. I'd have `quickstart.sql`, and models that copy it, including every CHECK constraint, default and index, so they could fall out of sync. That's not DRY at all.
    - My migration would go without being tested, since `create_all` builds `payments` from my model, and not migration. A bug in the migration would get past every test, and only show up for the reviewer.
    - I would produce unused models, which is against KISS.

5. So exactly what tables will I be using, and why just some of them. The reason I use some of the tables is because the endpoint only needs some of the data.

    How payments work:

    1. Stripe, Ayden or whatever payment provider stored the card and gave me a token, which is the `provider_token` column. To charge the card, I send the provider the token, the amount, and the currency.
    2. The provider then replies in one of these ways:
        
        - Succeeded. Money taken, I get a charge ID.
        - Declined. Bank refused. For instance, the card expired, or there are insufficient funds. Money were not moved.
        - No proper answer. Request timeout, network fail, something akin to that.
    
    ### The plan.

    I did some research on payments, and learned the following.

    Double charge is the worst bug possible. A double-click, a retry after a timeout, or two browser tabs - they all can start a charge.

    So I am going to:

    - Record the payment before calling the provider, so I always know a charge was attempted, even if the application crashed halfway through.
    - Send an idempotency key (HTTP Idempotency Key header), which is a unique ID for the attempt. Provider sees the key twice, returns the first result instead of charging again. I will use my payment's ID for this.
    - My database will reject a second active payment for the same card. For safety.

6. Designing the payments table.

    So I'm thinking: exactly what columns does my table need, in order to do what I wrote down in entry №5?

    So far, the table looks like this (I might update it later):

    ```
    id: UUID - The primary key. It's what I'll send as the idempotency key to the provider.
    card_id - This is the cart I am charging for.
    payment_method_id - This is the card I am charging.
    amount: NUMERIC(12,2), CHECK > 0 - How much I need to charge.
    curreny: CHAR(3) - The currency of the amount.
    status - How my payment went: pending, succeeded or failed, enforced with a CHEK constraint.
    provider_charge_id - The provider's charge ID, it's empty until the charge succeeds.
    failure_reason - Why the payment failed, for instance "card_expired".
    created_at, updated_at - Timestamps, as per base schema.

    Constraint for the status.
    Constraint for amount.
    ```
    Also, **unique**, **partial** index on cart_id. This will mean no two rows may have the same cart_id. Postgres checks this on each insert, so a second row for the same cart will fail with a unique violation error. Making it partial (`WHERE status IN`) will limit the index to only the rows that match it.

    With that logic, any number of failed charges are allowed for a cart. However, at most one pending or succeeded charge can exist at once, so if it's being charged or was already charged, it cannot be charged again.

    Researching the topic, I found out that the obvious check to "look for an active payment, and add one if there isn't any" breaks when several requests arrive together. Both could find no active payment, because neither inserted anything yet, so both insert their rows, and the customer is charged twice.

7. I noticed the NUMERIC(12, 2) priЁces on products. That means in theory we couldn't charge a cart with a total larger than ~9.9 billion. However, in practice, no card providers allow charges of such scale anyway, with most of them being capped at thousands to tens of thousands of USD. I'm using the same constraint for my Payments table. 

    I did a bit of research, and found out that if I ever need to change this, a one-lin migration, such as `ALTER COLUMN amount TYPE NUMERIC(14, 2)` fixes it, since widening a `NUMERIC` doesn't lose data.

8. So it's finally time to make a mock provider. What I'm thinking here: it's in the name - "mock". I'm guessing I'll just literally make a "provider" endpoint, or even just a function, which will return some response-like data for my service to work with.

    It'll do what is written in [TASK.md](TASK.md): fail or succeed. Howver, there's this third scenario, where the provider didn't answer due to unknown reasons. Handling that means the payment is left pending, and we'd check later. This is out of scope here.

    Same goes for refunds, 3D secure, and partial captures.

9. I shouldn't just add amounts up. In Python, `0.1 + 0.2 = 0.30000000000000004`. I will use `decimal.Decimal` instead.

10. So when we're charging, the code doesn't check each product for its currency type. Why? It could be GBP for all we know, but I still should not query `products` at payment time. The `cart_items` stores `unit_price`, so a later price change doesn't change the charge, and `products.currency` can change for the same reason. Reading it during a payment could charge a snapshotted price in a different currency.

    **Assumption I make**: The base schema doesn't store a currency on the cart item, and every sample product is USD, so I am going to treat the charge as USD. A mixed cart would be a real bug, and the schema allows it. Handling a cart, whose products are not all the same currency would mean loading `products` and comparing them, and that check lives in the service that adds items to the cart, not the one I am working on.

11. `payments/service.py`, I am loading the default card with `limit(1)`, and `.scalars().first()`, because the current schema allows for multiple default cards.

12. I made the payment service throw exceptions when something goes wrong, because that immediately rolls back the session, and nothing unexpected gets writted into the DB.

## Some planning for personal clarity.
Festina lente.

0. ~~Containerise everything. We are working in Docker. "Works on my machine" is unacceptable.~~
1. ~~Create a basic Flask project.~~
2. ~~Add the DB support and load the quickstart DB into it.~~
3. ~~Add Alembic.~~
4. ~~Design the payments table and migrate it into the DB~~.
5. ~~Add the Payment model and PaymentStatus enum to match what I wrote in Alembic.~~
6. ~~Create a mock provider.~~
7. ~~Add a payment service.~~
8. Add the enpoint. Parse the request, call the service, turn the result into an HTTP response with a proper status.
9. Add tests.
10. Create a nice README.
