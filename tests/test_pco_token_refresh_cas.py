from ordinarium.db import get_gateway_connection
from ordinarium.pco_client import PcoToken
from ordinarium.pco_store import (
    claim_pco_connection_refresh,
    complete_pco_connection_refresh,
    get_pco_connection,
    upsert_pco_connection,
)


def test_refresh_claim_is_versioned_and_stale_completion_cannot_overwrite(
    app, user_factory
):
    user_id = user_factory(email="refresh-cas@example.com")
    with app.app_context():
        db = get_gateway_connection()
        upsert_pco_connection(
            user_id,
            "access-old",
            "refresh-old",
            expires_at="2020-01-01T00:00:00+00:00",
            db=db,
        )
        original = get_pco_connection(user_id, db=db)
        claim = claim_pco_connection_refresh(original, db=db)
        overlapping = claim_pco_connection_refresh(original, db=db)
        completed = complete_pco_connection_refresh(
            original,
            claim,
            PcoToken(
                "access-new", "refresh-new", expires_at="2099-01-01T00:00:00+00:00"
            ),
            db=db,
        )
        stale = complete_pco_connection_refresh(
            original,
            claim,
            PcoToken("access-stale", "refresh-stale"),
            db=db,
        )
        current = get_pco_connection(user_id, db=db)

    assert claim
    assert overlapping is None
    assert completed is True
    assert stale is False
    assert current["access_token"] == "access-new"
    assert current["refresh_token"] == "refresh-new"
    assert current["version"] == original["version"] + 1
