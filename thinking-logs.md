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

## Some planning for personal clarity.
Festina lente.

0. Containerise everything. We are working in Docker. "Works on my machine" is unacceptable.
1. Create a basic Flask project.
2. Add the DB support and load the quickstart DB into it.
3. Add Alembic.
4. Design the payments table and migrate it into the DB.



