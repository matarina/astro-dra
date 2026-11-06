"""Role transitions and migration are tested against real SQLite transactions."""

import sqlite3
import pytest

from astro_accounts.store import AccountStore, validate_registration


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "auth.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL)")
        conn.execute("INSERT INTO users(id,username) VALUES (1,'existing_owner')")
    store = AccountStore(path)
    store.initialize()
    with store.connection(write=True) as conn:
        conn.execute("INSERT INTO users(id,username) VALUES (2,'root'),(3,'ordinary'),(4,'applicant')")
        conn.execute("""INSERT INTO astro_account_access(user_id,role,requested_role,review_state)
            VALUES (2,'root','user','none'),(3,'user','user','none'),(4,'user','admin','pending')""")
    return store


def test_migration_preserves_existing_admins_but_never_promotes_new_accounts(store):
    assert store.get("existing_owner").role == "admin"
    assert store.get("applicant").role == "user"
    with store.connection(write=True) as conn:
        conn.execute("INSERT INTO users(username) VALUES ('no_role_row')")
    store.initialize()
    assert store.get("no_role_row").role == "user"


@pytest.mark.parametrize("actor", ["existing_owner", "ordinary", "applicant", "missing"])
def test_only_root_can_review(store, actor):
    with pytest.raises(PermissionError):
        store.review(actor, 4, "approve")
    assert store.get("applicant").review_state == "pending"


def test_approve_and_revoke_are_persistent_and_audited(store):
    store.review("root", 4, "approve")
    assert AccountStore(store.path).get("applicant").is_admin
    with pytest.raises(ValueError):
        store.review("root", 4, "approve")
    store.review("root", 4, "revoke")
    assert not store.get("applicant").is_admin
    with store.connection() as conn:
        assert [r[0] for r in conn.execute("SELECT action FROM astro_account_audit ORDER BY id")] == ["approve", "revoke"]


def test_rejection_keeps_an_ordinary_account(store):
    store.review("root", 4, "reject")
    assert store.get("applicant").role == "user"
    assert store.get("applicant").review_state == "rejected"


def test_root_cannot_be_changed_or_created_through_registration(store):
    for username in ("root", "ROOT", "Root"):
        assert validate_registration(username, "user")
    for kind in ("root", "superadmin", "", "ADMIN"):
        assert validate_registration("new_user", kind)
    assert not validate_registration("new_user", "admin")
    with pytest.raises(PermissionError):
        store.review("root", 2, "revoke")


def test_migration_refuses_to_take_over_an_existing_root_name(tmp_path):
    path = tmp_path / "auth.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE)")
        conn.execute("INSERT INTO users VALUES (1,'root')")
    with pytest.raises(RuntimeError, match="ownership"):
        AccountStore(path).initialize()
