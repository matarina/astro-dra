"""Install role policy and small, version-checked hooks in the pinned native runtime."""

import argparse
import ast
import importlib.util
from pathlib import Path
import shutil
import sysconfig


def replace_once(content, old, new, label):
    if new in content:
        return content
    if content.count(old) != 1:
        raise ValueError(f"Incompatible native account hook: {label}")
    return content.replace(old, new, 1)


def candidates(package):
    app_path = package / "web/app_factory.py"
    auth_path = package / "web/auth/routes.py"
    settings_path = package / "settings/manager.py"
    database_path = package / "database/encrypted_db.py"
    auth_database_path = package / "database/auth_db.py"
    research_path = package / "web/routes/research_routes.py"
    scheduler_path = package / "scheduler/background.py"
    app = replace_once(app_path.read_text(),
        '    logger.info("Blueprints registered successfully")',
        '    logger.info("Blueprints registered successfully")\n\n'
        '    from astro_accounts.web import install as install_account_access\n'
        '    install_account_access(app)', "Flask installation")
    auth = replace_once(auth_path.read_text(),
        '    # Check if user already exists\n',
        '    from astro_accounts.store import validate_registration\n'
        '    errors.extend(validate_registration(username, request.form.get("account_type", "user")))\n\n'
        '    # Check if user already exists\n', "registration validation")
    auth = replace_once(auth,
        '            new_user_id = new_user.id\n            auth_db.commit()',
        '            new_user_id = new_user.id\n'
        '            from astro_accounts.store import record_registration\n'
        '            record_registration(auth_db, new_user_id, request.form.get("account_type", "user"))\n'
        '            auth_db.commit()', "atomic registration role")
    settings = replace_once(settings_path.read_text(),
        '        # First check if this is an env-only setting\n',
        '        from astro_accounts.policy import read_service_setting, UNMANAGED\n'
        '        controlled = read_service_setting(self, key, default, check_env)\n'
        '        if controlled is not UNMANAGED:\n'
        '            return controlled\n\n'
        '        # First check if this is an env-only setting\n', "settings read policy")
    settings = replace_once(settings,
        '        return result\n\n    def get_settings_snapshot(',
        '        from astro_accounts.policy import managed_settings_snapshot\n'
        '        return managed_settings_snapshot(self, result, include_environment_overrides)\n\n'
        '    def get_settings_snapshot(', "settings snapshot policy")
    database = replace_once(database_path.read_text(),
        '            self.connections[username] = engine',
        '            engine._astro_account_username = username\n'
        '            self.connections[username] = engine', "encrypted database owner")
    research = replace_once(research_path.read_text(),
        '    data = request.json\n    validation_error = validate_search_overrides(data)',
        '    from astro_accounts.policy import managed_research_input\n'
        '    data = managed_research_input(session.get("username"), request.json)\n'
        '    validation_error = validate_search_overrides(data)', "internal research entry")
    scheduler = replace_once(scheduler_path.read_text(),
        '        from ..config.thread_settings import set_settings_context\n',
        '        from ..config.thread_settings import set_settings_context\n'
        '        from astro_accounts.policy import managed_subscription\n'
        '        subscription = managed_subscription(username, subscription)\n', "scheduled research overrides")
    auth_database = replace_once(auth_database_path.read_text(),
        '            dbapi_connection.execute("PRAGMA busy_timeout = 10000")',
        '            dbapi_connection.execute("PRAGMA foreign_keys = ON")\n'
        '            dbapi_connection.execute("PRAGMA busy_timeout = 10000")', "registration role cleanup")
    result = {app_path: app, auth_path: auth, settings_path: settings, database_path: database,
              auth_database_path: auth_database, research_path: research, scheduler_path: scheduler}
    for path, content in result.items():
        ast.parse(content, filename=str(path))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.find_spec("local_deep_research")
    package = Path(next(iter(spec.submodule_search_locations)))
    replacements = candidates(package)  # Validate everything before mutating.
    for source in (args.source / "astro_accounts").glob("*.py"):
        ast.parse(source.read_text(), filename=str(source))
    shutil.copytree(args.source / "astro_accounts", Path(sysconfig.get_path("purelib")) / "astro_accounts",
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path, content in replacements.items():
        path.write_text(content)
        print("Account policy hook:", path.relative_to(package))


if __name__ == "__main__":
    main()
