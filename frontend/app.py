"""Frontend service: Flask + Jinja + vanilla JS.

Serves HTML only. Every piece of business data comes from the backend API,
called from the browser, so there is exactly one place where prices,
availability and feasibility are decided.

The backend URL is injected into the page as a data attribute rather than
hard-coded in JavaScript, so the same build runs in development and
production. No key or secret is ever placed in a template.
"""

from __future__ import annotations

import os

from flask import Flask, render_template


def create_app() -> Flask:
    app = Flask(__name__)

    app.config.update(
        APP_ENV=os.environ.get("APP_ENV", "development"),
        APP_NAME=os.environ.get("APP_NAME", "Mayan's Cake Factory"),
        BACKEND_URL=os.environ.get("BACKEND_URL", "http://localhost:8001"),
    )

    @app.context_processor
    def inject_config() -> dict[str, str]:
        # Available to every template. Contains no credentials by design.
        return {
            "app_name": app.config["APP_NAME"],
            "backend_url": app.config["BACKEND_URL"],
            "app_env": app.config["APP_ENV"],
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/orders/<order_number>")
    def order_confirmation(order_number: str):
        """Order confirmation, reachable by order number so the customer can
        return to it later without an account."""
        return render_template("confirmation.html", order_number=order_number)

    @app.get("/design/preview")
    def design_preview():
        """Design preview, revisions and version history."""
        return render_template("preview.html")

    @app.get("/design/summary")
    def design_summary():
        """The confirmation gate before image generation."""
        return render_template("summary.html")

    @app.get("/design")
    def design():
        """The AI design conversation. The session token is held in the
        browser's sessionStorage, so this route needs no state of its own."""
        return render_template("design.html")

    @app.get("/admin/login")
    def admin_login():
        return render_template("admin_login.html")

    @app.get("/admin")
    def admin_dashboard():
        return render_template("admin_dashboard.html")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "frontend", "environment": app.config["APP_ENV"]}

    return app


app = create_app()

if __name__ == "__main__":
    # Railway supplies PORT; never hard-code it.
    # Binding all interfaces is required inside a container; Railway
    # terminates TLS and routes traffic to this port.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)  # noqa: S104
