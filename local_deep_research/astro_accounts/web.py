"""Flask integration; roles are read from the server, never from form/cookie claims."""

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

from .store import AccountStore

PERSONAL_SETTINGS = {
    "app.theme", "research_library.confirm_deletions", "research_library.auto_index_enabled",
    "document_scheduler.generate_rag", "document_scheduler.enabled",
    "document_scheduler.sweep_library_collections",
}
ZOTERO_SETTINGS = {"zotero." + name for name in (
    "enabled", "use_local_api", "library_type", "library_id", "collection_keys", "import_items_without_pdf",
    "import_annotations", "import_tags", "pdf_storage_mode", "auto_sync_enabled", "sync_interval_minutes", "api_key")}
ADMIN_BLUEPRINTS = {"metrics", "benchmark", "context_overflow_api", "api_v1"}
ADMIN_ENDPOINTS = {
    "research.settings_page", "research.save_raw_config", "research.open_file_location",
    "api.get_current_config", "api.check_ollama_status", "api.check_ollama_model",
    "rag.embedding_settings_page", "rag.test_embedding", "rag.get_embedding_models", "rag.configure_rag",
}
ADMIN_PATHS = {
    "/settings", "/library/embedding-settings", "/library/api/rag/test-embedding",
    "/library/api/rag/models", "/library/api/rag/configure", "/open_file_location", "/api/save_raw_config",
}
RUN_CONFIG_FIELDS = {"model_provider", "model", "custom_endpoint", "search_engine", "search_tool",
                     "iterations", "search_iterations", "questions_per_iteration", "strategy", "search_strategy",
                     "policy_egress_scope", "llm_require_local_endpoint", "embeddings_require_local", "settings_snapshot"}


def _personal_setting(key):
    return key in PERSONAL_SETTINGS | ZOTERO_SETTINGS or key.startswith("app.ui.help_dismissed_")


def _forbidden():
    message = "此功能仅向管理员开放。研究所需配置由服务端统一提供。"
    if request.is_json or "/api/" in request.path or request.path.endswith("/api"):
        return jsonify({"status": "error", "error": message, "message": message}), 403
    return render_template("auth/forbidden.html", message=message), 403


def install(app):
    if "astro_accounts" in app.extensions:
        return
    from local_deep_research.database.auth_db import init_auth_database
    from local_deep_research.web.auth.decorators import login_required

    init_auth_database()
    store = AccountStore()
    store.initialize()
    app.extensions["astro_accounts"] = store
    bp = Blueprint("astro_accounts", __name__)

    @app.before_request
    def account_access():
        # Native middleware has already validated the server-side session.
        username = session.get("username")
        g.astro_account = store.get(username) if username else None
        account = g.astro_account
        if not username:
            return None
        if not account:
            if request.path.startswith(("/auth/", "/static/")):
                return None
            return _forbidden()
        if account.is_admin:
            return None
        endpoint = request.endpoint or ""
        if request.blueprint in ADMIN_BLUEPRINTS or endpoint in ADMIN_ENDPOINTS or request.path.rstrip("/") in ADMIN_PATHS:
            return _forbidden()
        if request.path.startswith("/news/api/scheduler/") and request.path.rsplit("/", 1)[-1] != "status":
            return _forbidden()
        if request.blueprint == "settings":
            if endpoint == "settings.save_all_settings" and request.is_json:
                data = request.get_json(silent=True)
                if isinstance(data, dict) and data and set(data) <= ZOTERO_SETTINGS:
                    return None
            if endpoint in {"settings.api_get_db_setting", "settings.api_update_setting"}:
                if _personal_setting((request.view_args or {}).get("key", "")):
                    return None
            if endpoint == "settings.get_bulk_settings" and request.method == "GET":
                keys = request.args.getlist("keys[]")
                if keys and all(_personal_setting(key) for key in keys):
                    return None
            return _forbidden()
        if (request.blueprint or "").split(".")[0] in {"news", "news_api"} and request.method in {"POST", "PUT", "PATCH"}:
            data = request.get_json(silent=True)
            if isinstance(data, dict) and any(data.get(key) not in (None, "") for key in RUN_CONFIG_FIELDS):
                return _forbidden()
        if endpoint in {"research.start_research", "api.api_start_research"} and request.method == "POST":
            data = request.get_json(silent=True)
            if isinstance(data, dict):
                # Prevent per-run overrides (including nested metadata) before
                # native extraction, queue snapshots, or any model call occurs.
                unexpected = set(data) - {"query", "mode", "metadata"}
                metadata = data.get("metadata", {})
                metadata_ok = isinstance(metadata, dict) and not (set(metadata) - {
                    "is_news_search", "triggered_by", "subscription_id", "parent_research_id", "search_type", "display_in",
                    "original_query", "processed_query", "news_date", "title"})
                if unexpected or not metadata_ok:
                    return _forbidden()
        return None

    @app.context_processor
    def account_context():
        account = getattr(g, "astro_account", None)
        return {"astro_is_admin": bool(account and account.is_admin),
                "astro_is_root": bool(account and account.is_root),
                "astro_account": account}

    @bp.route("/account/access", methods=["GET"])
    @login_required
    def access_status():
        account = store.get(session["username"])
        if not account:
            abort(403)
        return jsonify({"role": account.role, "review_state": account.review_state})

    @bp.route("/admin/accounts", methods=["GET"])
    @login_required
    def accounts():
        account = store.get(session["username"])
        if not account or not account.is_root:
            return _forbidden()
        return render_template("auth/accounts.html", accounts=store.list_accounts(), active_page="accounts")

    @bp.route("/admin/accounts/<int:user_id>/<action>", methods=["POST"])
    @login_required
    def review(user_id, action):
        try:
            store.review(session["username"], user_id, action)
        except PermissionError:
            return _forbidden()
        except LookupError:
            abort(404)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("astro_accounts.accounts")), 303
        flash({"approve": "已批准管理员申请。", "reject": "已拒绝申请，账号保留普通用户权限。",
               "revoke": "已将该账号调整为普通用户。"}[action], "success")
        return redirect(url_for("astro_accounts.accounts")), 303

    app.register_blueprint(bp)
