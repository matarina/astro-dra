"""Apply server defaults/env at the settings seam, including background workers."""

from pathlib import Path

from .store import AccountStore

UNMANAGED = object()
SERVICE_PREFIXES = ("llm.", "search.", "embeddings.", "rag.", "policy.", "report.", "chat.", "benchmark.", "rate_limiting.")


def service_owned(key):
    return any(key == prefix[:-1] or key.startswith(prefix) for prefix in SERVICE_PREFIXES)


def _database_is_managed(db_session):
    if db_session is None:
        return False
    from local_deep_research.config.paths import get_user_database_filename
    bind = db_session.get_bind()
    username = getattr(bind, "_astro_account_username", None)
    if username:
        account = AccountStore().get(username)
        return not account or not account.is_admin
    database = bind.url.database
    filename = Path(database).name if database else ""
    if not filename.startswith("ldr_user_"):
        return False
    # Cache identity, never authorization. Re-check role on every operation so a
    # root revocation applies to existing sessions and background task dispatch.
    info = db_session.info
    if "astro_account_owner" not in info:
        info["astro_account_owner"] = next((a.username for a in AccountStore().list_accounts()
            if get_user_database_filename(a.username) == filename), None)
    username = info["astro_account_owner"]
    account = AccountStore().get(username) if username else None
    return not account or not account.is_admin


def read_service_setting(manager, key, default=None, check_env=True):
    if not service_owned(key) or not _database_is_managed(manager.db_session):
        return UNMANAGED
    from local_deep_research.settings.manager import get_typed_setting_value
    values = {}
    for name, meta in manager.default_settings.items():
        if name == key or name.startswith(key + "."):
            values[name] = get_typed_setting_value(name, meta.get("value"), meta.get("ui_element", "text"),
                                                   default=meta.get("value"), check_env=check_env)
    if key in values:
        return values[key]
    if values:
        return {name[len(key) + 1:]: value for name, value in values.items()}
    # No custom provider/engine key may leak in from a user's legacy DB.
    return default


def managed_settings_snapshot(manager, result, include_environment_overrides=True):
    if not _database_is_managed(manager.db_session):
        return result
    from local_deep_research.settings.manager import SettingsManager
    canonical = SettingsManager().get_all_settings(include_environment_overrides=include_environment_overrides)
    filtered = {key: value for key, value in result.items() if not service_owned(key)}
    for key, meta in canonical.items():
        if service_owned(key):
            filtered[key] = {**meta, "editable": False}
    return filtered


def managed_research_input(username, data):
    """Also covers native in-process subscription calls that skip Flask hooks."""
    account = AccountStore().get(username) if username else None
    if not username or (account and account.is_admin) or not isinstance(data, dict):
        return data
    return {key: value for key, value in data.items() if key in {"query", "mode", "metadata"}}


def managed_subscription(username, subscription):
    account = AccountStore().get(username)
    if account and account.is_admin:
        return subscription
    return {**subscription, **{key: None for key in (
        "model_provider", "model", "search_strategy", "search_engine", "custom_endpoint",
        "search_iterations", "questions_per_iteration")}}
