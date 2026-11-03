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

2. In this task, I will not necessarily use all the tables from `quickstart.sql`. Therefore, to keep it simple, I won't be mapping all of them to Alchemy models. This, in turn, means that when I do map the ones I need, Alembic's autogenerate will propose a drop_table for the tables that exist in the database, but not in my models.

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

    1. Stripe, Adyen or whatever payment provider stored the card and gave me a token, which is the `provider_token` column. To charge the card, I send the provider the token, the amount, and the currency.
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
    cart_id - This is the cart I am charging for.
    payment_method_id - This is the card I am charging.
    amount: NUMERIC(12,2), CHECK > 0 - How much I need to charge.
    currency: CHAR(3) - The currency of the amount.
    status - How my payment went: pending, succeeded or failed, enforced with a CHECK constraint.
    provider_charge_id - The provider's charge ID, it's empty until the charge succeeds.
    failure_reason - Why the payment failed, for instance "card_expired".
    created_at, updated_at - Timestamps, as per base schema.

    Constraint for the status.
    Constraint for amount.
    ```
    Also, **unique**, **partial** index on cart_id. This will mean no two rows may have the same cart_id. Postgres checks this on each insert, so a second row for the same cart will fail with a unique violation error. Making it partial (`WHERE status IN`) will limit the index to only the rows that match it.

    With that logic, any number of failed charges are allowed for a cart. However, at most one pending or succeeded charge can exist at once, so if it's being charged or was already charged, it cannot be charged again.

    Researching the topic, I found out that the obvious check to "look for an active payment, and add one if there isn't any" breaks when several requests arrive together. Both could find no active payment, because neither inserted anything yet, so both insert their rows, and the customer is charged twice.

7. I noticed the NUMERIC(12, 2) prices on products. That means in theory we couldn't charge a cart with a total larger than ~9.9 billion. However, in practice, no card providers allow charges of such scale anyway, with most of them being capped at thousands to tens of thousands of USD. I'm using the same constraint for my Payments table. 

    I did a bit of research, and found out that if I ever need to change this, a one-line migration, such as `ALTER COLUMN amount TYPE NUMERIC(14, 2)` fixes it, since widening a `NUMERIC` doesn't lose data.

8. So it's finally time to make a mock provider. What I'm thinking here: it's in the name - "mock". I'm guessing I'll just literally make a "provider" endpoint, or even just a function, which will return some response-like data for my service to work with.

    It'll do what is written in [TASK.md](TASK.md): fail or succeed. However, there's this third scenario, where the provider didn't answer due to unknown reasons. Handling that means the payment is left pending, and we'd check later. This is out of scope here.

    Same goes for refunds, 3D secure, and partial captures.

9. I shouldn't just add amounts up. In Python, `0.1 + 0.2 = 0.30000000000000004`. I will use `decimal.Decimal` instead.

10. So when we're charging, the code doesn't check each product for its currency type. Why? It could be GBP for all we know, but I still should not query `products` at payment time. The `cart_items` stores `unit_price`, so a later price change doesn't change the charge, and `products.currency` can change for the same reason. Reading it during a payment could charge a snapshotted price in a different currency.

    **Assumption I make**: The base schema doesn't store a currency on the cart item, and every sample product is USD, so I am going to treat the charge as USD. A mixed cart would be a real bug, and the schema allows it. Handling a cart, whose products are not all the same currency would mean loading `products` and comparing them, and that check lives in the service that adds items to the cart, not the one I am working on.

11. `payments/service.py`, I am loading the default card with `limit(1)`, and `.scalars().first()`, because the current schema allows for multiple default cards.

12. I made the payment service throw exceptions when something goes wrong, because that immediately rolls back the session, and nothing unexpected gets written into the DB.

13. Now that I'm done with the payment service, it is time to create the endpoint. First of all, since the app has neither authentication nor authorization, the endpoint is going to assume that the cart's owner is our user, and therefore there is no `user_id` in the parameters. What I do need is `cart_id`, which is the cart to charge. It is a mandatory parameter, and if it's missing, or is an invalid UUID value, that's a 400. We also have a `payment_method_id`, which isn't required (because the user has a default card, or rather - could have it), although it will still return a 400, if it's an invalid UUID.

    ### So what codes am I going to return and why?

    201 Created. A payment row was created and the card was charged. The body is that payment, including provider_charge_id.

    402 Payment Required. The request was valid and a payment row was saved, but the provider declined the card. The body includes failure_reason. 402 is the status Stripe uses for a refused card, and it lets the client show "try another card" without inspecting the body. The cart stays active, so the same request can be repeated with a different card.

    400 Bad Request. The request itself is malformed: no JSON, no cart_id, or a value that is not a UUID. Retrying the same bytes will fail again. The client has to change the request.

    404 Not Found. The UUID is well formed, and no row has that id. This covers an unknown cart and an unknown card.

    403 Forbidden. The card exists, and it belongs to a different user. The caller is not allowed to charge it.

    409 Conflict. The request is well formed, and it conflicts with the cart's current state. The cart is already checked_out or abandoned, or a pending or succeeded payment already exists. The same request can succeed later only if that state changes, which for a paid cart it will not.

    422 Unprocessable Content. The JSON and the UUIDs are valid, and the cart exists, but there is nothing to charge. The cart has no items, or the user has no default card and did not send one. Changing the request, or adding items, is what makes it succeed.

    500 is for anything else, including a cart whose total is 0.00. That fails the database check and is not a duplicate payment, so it is not turned into a 409.

14. What test suite should I use? I dug around some, and realised that unittest wouldn't cut it here, or rather it wouldn't be the best solution. Its setup lives in setUp and setUpClass, and it gets sketchy when a test needs both a migrated Postgres, and a test client. Also `parametrize`. Without it, I'd have to repeat myself, copying the same test with different parameters, or write crutches inside the test itself, with loops and whatnot.

    So exactly what scenarios should I test for? We have: every exception I added, a successful payment, a failed payment, and... I think that's about it, honestly.

    Wait, no there's more.
    
    Tests should also have their own database, and load `quickstart.sql` into it, so it's independent, and also covers the fact that the seed itself loads, and migrations work. I shall build each test's own user, cart, items and the payment token.

    Also, I need to test when the request is rejected before the service runs, and no payment row is created. Missing body, body that isn't JSON, missing cart_id, weird payment_id, the works. That's probably it.

    Wait, no - if I change products.price before paying, the amount charged should stay at cart_items.unit_price, that's literally one of the points I made earlier.

    ### How do the tests work
    After yet more research, this is how everything is going to work.

    1. `_prepare_database` runs once, it rebuilds `shop_test` from ground up.
         
         It connects to the main database because `CREATE DATABASE` cannot run while you are connected to the database you are creating, and `autocommit=True` is required for the same reason of `CREATE DATABASE` not being possible inside a transaction in Postgres.

         `DROP DATABASE` with `FORCE` disconnects anything still connected, including leftover connections, and deletes shop_test. Then it's created empty.

         `quickstart.sql` is split. This is because psycopg runs one statement per call, and that file creates users, products, carts, cart_items, and user_payment_methods, and it also inserts Alice. It DOES NOT create payments.

         Alembic is then ran, its `upgrade head` invoked against `shop_test`. The URL is set on the config before upgrade is ran, and `env.py` only uses the default DATABASE_URL when that option is empty, so the migration goes to the test database, and not the main one. "%" is doubled because as stated in previous logs, Alembic treats % as a placeholder.
    
    2. `app` is a session scoped fixture. It means the database is built once per pytest run, not once per test. `create_app` uses the TEST_DATABASE_URL, `TESTING: True` means Flask test client will raise unexpected exceptions instead of returning a 500 page. When the last test is finished, the session is removed, and the engine's connections are closed.

    3. `client` this is a fixture, which returns a Flask's test client, as per the [Flask docs](https://flask.palletsprojects.com/en/stable/testing/).

    4. `Shop` is there to build the rows the client needs. It's basically our seeding tool. There is an `expunge_all` call for payments, it detaches the rows with their values loaded, so when we read the payment status, we don't get a detached instance error.

    5. `_commit` runs an insert inside an app context, commits and removes the session. `_read` does the same, but it doesn't commit. These methods open and close their own contexts, so the test client always gets a fresh session for the request.

    6. `shop`'s TRUNCATE empties every shop table, including Alice from quickstart.sql, and RESTART IDENTITY resets primary keys and such, basically all sequentially incrementing values to their starting one, usually 1. In other words, it's a reset so the tests don't contaminate each other. Alembic version isn't truncated, so the migration isn't ran over and over again.

    7. **Misc things.**

        I did a little bit of digging and found out Stripe puts `tok_` before a card token, so the seed data follows it. Same with Alice's card.

        `@pytest.mark.parametrize` allows you to run a single test function multiple times using different sets of data. Having used unittest most of my time before, I find this a very nifty tool.

        During testing I found a bug: the failed constraint for non-zero amount would be picked up and returned as a PaymentAlreadyExistsError. So I added a check for that, and also tested it just in case.

    

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
8. ~~Add the endpoint. Parse the request, call the service, turn the result into an HTTP response with a proper status.~~
9. ~~Add tests.~~
10. ~~Create a nice README.~~
