import os

from flask import Flask, jsonify


def _create_private_container_app(default_role):
    app = Flask(f"ordinarium.{default_role}")
    role = os.environ.get("ORDINARIUM_CONTAINER_ROLE", default_role)

    @app.get("/health")
    def health():
        return jsonify({"role": role, "status": "ok"})

    return app


def create_documents_app():
    return _create_private_container_app("documents")


def create_jobs_app():
    return _create_private_container_app("jobs")
