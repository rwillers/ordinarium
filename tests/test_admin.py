from ordinarium.db import get_db


def test_admin_requires_login(client):
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_denies_without_flag(auth_client):
    client, _ = auth_client
    response = client.get("/admin")
    assert response.status_code == 404


def test_admin_allows_with_flag(app, auth_client):
    client, user_id = auth_client
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"admin": true}', user_id),
        )
        db.commit()
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Users" in response.data


def test_admin_user_delete_soft_deletes_user(app, auth_client, user_factory):
    client, admin_id = auth_client
    user_id = user_factory(email="delete-me@example.com")
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"admin": true}', admin_id),
        )
        db.commit()

    response = client.post(f"/admin/users/{user_id}/delete")
    assert response.status_code == 302

    with app.app_context():
        db = get_db()
        deleted_at = db.execute(
            "select deleted_at from users where id=? limit 1", (user_id,)
        ).fetchone()["deleted_at"]
        assert deleted_at is not None
        visible = db.execute(
            "select id from users where id=? and deleted_at is null limit 1",
            (user_id,),
        ).fetchone()
        assert visible is None


def test_admin_bulk_delete_soft_deletes_users(app, auth_client, user_factory):
    client, admin_id = auth_client
    user_id_one = user_factory(email="bulk-one@example.com")
    user_id_two = user_factory(email="bulk-two@example.com")
    with app.app_context():
        db = get_db()
        db.execute(
            "update users set feature_flags=? where id=?",
            ('{"admin": true}', admin_id),
        )
        db.commit()

    response = client.post(
        "/admin/users/bulk-delete",
        data={"user_ids": [str(user_id_one), str(admin_id), str(user_id_two)]},
    )
    assert response.status_code == 302

    with app.app_context():
        db = get_db()
        deleted_users = db.execute(
            "select id from users where deleted_at is not null and id in (?, ?)",
            (user_id_one, user_id_two),
        ).fetchall()
        assert len(deleted_users) == 2
        self_deleted = db.execute(
            "select deleted_at from users where id=? limit 1", (admin_id,)
        ).fetchone()["deleted_at"]
        assert self_deleted is None
