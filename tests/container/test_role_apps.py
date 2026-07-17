from container_role_apps import create_documents_app, create_jobs_app


def test_documents_health_endpoint():
    response = create_documents_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"role": "documents", "status": "ok"}


def test_jobs_health_endpoint(monkeypatch):
    monkeypatch.setenv("ORDINARIUM_CONTAINER_ROLE", "email-jobs")

    response = create_jobs_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"role": "email-jobs", "status": "ok"}


def test_private_container_apps_do_not_expose_business_routes():
    for app in (create_documents_app(), create_jobs_app()):
        response = app.test_client().get("/")

        assert response.status_code == 404
