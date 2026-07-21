"""UI tests for the Compare Jurisdictions page (pages/compare.py).

Runs the real page script via Streamlit's AppTest harness with DB calls
stubbed. Regression coverage for the KeyError raised when the flat
jurisdiction list had fewer than two entries (second selectbox empty ->
selection None -> jurisdiction_map[None]).
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from legal_ai.auth import jwt_utils

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPARE_FILE = str(PROJECT_ROOT / "pages" / "compare.py")

USER_ID = "11111111-1111-1111-1111-111111111111"


def _jur(name: str) -> dict:
    return {
        "jurisdiction_id": f"id-{name.lower().replace(' ', '-')}",
        "code": name.upper()[:8],
        "name": name,
        "level": "country",
        "flag_emoji": None,
        "region_code": None,
    }


def _signed_in_apptest(monkeypatch, jurisdictions: list[dict]) -> AppTest:
    from legal_ai import db

    monkeypatch.setattr(db, "ensure_db", lambda: None)
    monkeypatch.setattr(db, "get_all_jurisdictions", lambda: jurisdictions)

    at = AppTest.from_file(COMPARE_FILE, default_timeout=30)
    at.session_state["legal_ai_user_id"] = USER_ID
    at.session_state["legal_ai_user_email"] = "tester@example.com"
    at.session_state["legal_ai_access_token"] = jwt_utils.create_access_token(USER_ID)
    at.session_state["legal_ai_refresh_token"] = "refresh-token"
    at.session_state["legal_ai_user_role"] = "viewer"
    return at


def test_single_jurisdiction_shows_notice_not_crash(monkeypatch):
    """With only the WORLD root available the page must stop gracefully."""
    at = _signed_in_apptest(monkeypatch, [_jur("World")])
    at.run()

    assert not at.exception, f"Page raised: {at.exception}"
    assert len(at.selectbox) == 0
    infos = " ".join(i.value for i in at.info)
    assert "At least two jurisdictions" in infos


def test_two_selectors_populated_and_disjoint(monkeypatch):
    """With several jurisdictions both selectboxes render real choices."""
    at = _signed_in_apptest(
        monkeypatch, [_jur("Austria"), _jur("Belgium"), _jur("California")]
    )
    at.run()

    assert not at.exception, f"Page raised: {at.exception}"
    assert len(at.selectbox) == 2
    first, second = at.selectbox[0], at.selectbox[1]
    assert first.options == ["Austria", "Belgium", "California"]
    # The second selector excludes whatever the first one selected.
    assert first.value not in second.options
    assert second.value is not None
