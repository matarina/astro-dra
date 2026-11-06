"""Local-only root provisioning. Reads the initial password from stdin, never argv."""

import json
import sys

from .store import AccountStore


def main():
    from local_deep_research.database.auth_db import auth_db_session, init_auth_database
    from local_deep_research.database.encrypted_db import db_manager
    from local_deep_research.database.models.auth import User
    from local_deep_research.security.password_validator import PasswordValidator
    from sqlalchemy import text

    init_auth_database()
    store = AccountStore()
    store.initialize()
    existing = store.get("root")
    if existing:
        if not existing.is_root:
            raise RuntimeError("Existing root username is not the provisioned root; refusing to promote it")
        print(json.dumps({"root": "exists", "password_changed": False}))
        return
    password = sys.stdin.read().strip()
    if PasswordValidator.validate_strength(password):
        raise ValueError("Initial root password does not meet server requirements")
    user_id = None
    try:
        with auth_db_session() as auth:
            user = User(username="root")
            auth.add(user)
            auth.flush()
            user_id = user.id
            auth.execute(text("""INSERT INTO astro_account_access(user_id,role)
                VALUES (:id,'root')"""), {"id": user_id})
            # Hold the central transaction until encrypted DB creation succeeds.
            # Registration cannot claim the reserved name through HTTP.
            db_manager.create_user_database("root", password)
            auth.commit()
    finally:
        db_manager.close_user_database("root")
    print(json.dumps({"root": "created", "password_changed": False}))


if __name__ == "__main__":
    main()
