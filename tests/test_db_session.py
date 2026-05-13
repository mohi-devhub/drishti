from drishti.config import Settings
from drishti.db import session as db_session


def test_asyncpg_prepared_statement_cache_is_disabled(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(db_session, "create_async_engine", fake_create_async_engine)

    db_session.create_engine(
        Settings(database_url="postgresql+asyncpg://postgres:postgres@example.test:5432/drishti")
    )

    connect_args = captured["kwargs"]["connect_args"]  # type: ignore[index]
    assert connect_args["prepared_statement_cache_size"] == 0
    assert connect_args["statement_cache_size"] == 0
