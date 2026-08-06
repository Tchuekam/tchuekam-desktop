import re
import pytest

from agent.insights import InsightsEngine
from hermes_state import SessionDB


def test_session_cols_no_injection_chars():
    """_SESSION_COLS must not contain SQL injection vectors."""
    cols = InsightsEngine._SESSION_COLS
    assert ";" not in cols
    assert "--" not in cols
    assert "'" not in cols
    assert "DROP" not in cols.upper()


def test_get_sessions_all_query_is_parameterized():
    """_GET_SESSIONS_ALL must use a ? placeholder for the cutoff value."""
    query = InsightsEngine._GET_SESSIONS_ALL
    assert "?" in query
    assert "started_at >= ?" in query
    # Must not embed any runtime-variable content via brace interpolation
    assert "{" not in query


def test_get_sessions_with_source_query_is_parameterized():
    """_GET_SESSIONS_WITH_SOURCE must use ? placeholders for both parameters."""
    query = InsightsEngine._GET_SESSIONS_WITH_SOURCE
    assert query.count("?") == 2
    assert "started_at >= ?" in query
    assert "source = ?" in query
    assert "{" not in query


def test_session_col_names_are_safe_identifiers():
    """Every column name listed in _SESSION_COLS must be a simple identifier."""
    cols = InsightsEngine._SESSION_COLS
    identifiers = [c.strip() for c in cols.split(",")]
    safe_identifier = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    for col in identifiers:
        assert safe_identifier.match(col), (
            f"Column name {col!r} is not a safe SQL identifier"
        )


# ── Integration tests executing SQL injection payloads against SessionDB ─────


@pytest.fixture
def session_db(tmp_path):
    db_path = tmp_path / "test_sqli.db"
    db = SessionDB(db_path=db_path)
    yield db
    db.close()


def test_sqli_get_session_escapes_payload(session_db):
    """Passing malicious session_id to get_session must look up literal string and not execute SQL."""
    session_db.create_session("s1", source="cli")
    payload = "s1' OR '1'='1"
    res = session_db.get_session(payload)
    assert res is None

    drop_payload = "s1'; DROP TABLE sessions; --"
    res_drop = session_db.get_session(drop_payload)
    assert res_drop is None

    # Table must still exist and s1 must still be intact
    assert session_db.get_session("s1") is not None


def test_sqli_create_session_source_escapes_payload(session_db):
    """Malicious source parameter in create_session must be stored literally."""
    payload = "cli' IS NOT NULL; DELETE FROM sessions; --"
    session_db.create_session("s_malicious", source=payload)

    session = session_db.get_session("s_malicious")
    assert session is not None
    assert session["source"] == payload


def test_sqli_search_messages_fts5_escapes_payload(session_db):
    """Malicious query in search_messages must not trigger SQL syntax errors or injections."""
    session_db.create_session("s1", source="cli")
    session_db.append_message("s1", role="user", content="hello world secret_data")

    bad_queries = [
        "' OR '1'='1",
        "hello' AND DROP TABLE messages; --",
        '"NEAR/2 ("hello" "world")',
        "MATCH 'select * from sessions'",
    ]
    for q in bad_queries:
        results = session_db.search_messages(q)
        assert isinstance(results, list)


def test_sqli_insights_engine_escapes_source(session_db):
    """InsightsEngine query with malicious source must not return unallowed sessions."""
    session_db.create_session("s_valid", source="cli")
    session_db.create_session("s_secret", source="secret_channel")

    engine = InsightsEngine(db=session_db)
    injected_source = "cli' OR source='secret_channel"
    report = engine.generate(days=30, source=injected_source)
    assert report.get("empty") is True
