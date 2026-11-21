"""Connections for local SQLite and hosted PostgreSQL."""
import sqlite3

from .config import settings


def open_connection(sqlite_path: str, readonly: bool = False):
    if settings.database_url:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(settings.database_url, row_factory=dict_row)
        if readonly:
            connection.execute("SET TRANSACTION READ ONLY")
        return connection

    if readonly:
        connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    return connection


def execute(connection, statement: str, params=()):
    if settings.database_url and params:
        statement = statement.replace("?", "%s")
    return connection.execute(statement, params)
