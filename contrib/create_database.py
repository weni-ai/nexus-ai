import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def create_database(host: str, database: str, user: str, password: str) -> None:
    try:
        con = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
        )
        con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    except Exception as e:
        raise Exception("Could not connect to database")

    cur = con.cursor()

    try:
        cur.execute(f"CREATE USER {user} with PASSWORD '{password}'")
        cur.execute(f"ALTER ROLE {user} WITH SUPERUSER")
        cur.execute(f"CREATE DATABASE {database}")
    except Exception as e:
        raise e
    
    cur.close()
    con.close()


if __name__ == "__main__":
    create_database(
        host=os.environ.get("CI_POSTGRES_HOST", "postgres"),
        database=os.environ.get("CI_POSTGRES_DATABASE", "nexus"),
        user=os.environ.get("CI_POSTGRES_USER", "nexus"),
        password=os.environ.get("CI_POSTGRES_PASSWORD", "postgres"),
    )
