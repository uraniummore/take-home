# Logging thoughts here.

Right. First things first - I have an empty folder, which I have to turn into a Flask project with SQLAlchemy. The task is described in [TASK.md](TASK.md), and some of the context is also present in the commented part of the `quickstart.sql` file.

## What are some of the missable points? I will update this as I find them.

The task says "use your best judgement" for any missing context. Therefore, there are some assumptions I will make.

1. The **task** itself doesn't say this out loud, but the first thing I noticed is the word "migration", so I shall assume this means that I must add **Alembic** to my scope.

    > -- Run this file on an empty database before you start the task.
    <br> ... <br>
    -- This file does not define the payments table.
    <br>-- You design that part yourself. Add it as a new migration.

    The author likely wants me to first create the DB, and then migrate a new table for the payment.


## Some planning for personal clarity.
Festina lente.

0. Containerise everything. We are working in Docker. "Works on my machine" is unacceptable.
1. Create a basic Flask project.
2. Add the DB support.
3. Add Alembic.
4. We shall see what I put here next.
