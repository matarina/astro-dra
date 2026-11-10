"""Role metadata lives beside native users; passwords remain in native SQLCipher DBs."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Account:
    id: int
    username: str
    role: str
    requested_role: str
    review_state: str

    @property
    def is_admin(self):
        return self.role in {"admin", "root"}

    @property
    def is_root(self):
        return self.role == "root"


class AccountStore:
    def __init__(self, path=None):
        if path is None:
            from local_deep_research.database.auth_db import get_auth_db_path
            path = get_auth_db_path()
        self.path = Path(path)

    @contextmanager
    def connection(self, write=False):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        """One-time migration preserves existing accounts as administrators."""
        with self.connection(write=True) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS astro_account_access (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin','root')),
                requested_role TEXT NOT NULL DEFAULT 'user' CHECK(requested_role IN ('user','admin')),
                review_state TEXT NOT NULL DEFAULT 'none' CHECK(review_state IN ('none','pending','approved','rejected')),
                reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT,
                CHECK(role != 'root' OR requested_role = 'user')
            )""")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS astro_one_root ON astro_account_access(role) WHERE role='root'")
            conn.execute("""CREATE TABLE IF NOT EXISTS astro_account_audit (
                id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
                target_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS astro_account_migrations (name TEXT PRIMARY KEY)")
            migrated = conn.execute("SELECT 1 FROM astro_account_migrations WHERE name='roles_v1'").fetchone()
            if not migrated:
                # root is never silently granted to an existing public account.
                if conn.execute("SELECT 1 FROM users WHERE lower(username)='root'").fetchone():
                    raise RuntimeError("Reserved root account already exists; resolve its ownership before enabling roles")
                conn.execute("""INSERT INTO astro_account_access(user_id,role)
                    SELECT id,'admin' FROM users WHERE id NOT IN (SELECT user_id FROM astro_account_access)""")
                conn.execute("INSERT INTO astro_account_migrations(name) VALUES ('roles_v1')")

    @staticmethod
    def _account(row):
        return Account(**dict(row)) if row else None

    def get(self, username):
        with self.connection() as conn:
            row = conn.execute("""SELECT u.id,u.username,coalesce(a.role,'user') role,
                coalesce(a.requested_role,'user') requested_role,coalesce(a.review_state,'none') review_state
                FROM users u LEFT JOIN astro_account_access a ON a.user_id=u.id
                WHERE u.username=?""", (username,)).fetchone()
            return self._account(row)

    def list_accounts(self):
        with self.connection() as conn:
            rows = conn.execute("""SELECT u.id,u.username,coalesce(a.role,'user') role,
                coalesce(a.requested_role,'user') requested_role,coalesce(a.review_state,'none') review_state
                FROM users u LEFT JOIN astro_account_access a ON a.user_id=u.id
                ORDER BY CASE WHEN a.review_state='pending' THEN 0 ELSE 1 END,u.id""").fetchall()
            return [self._account(row) for row in rows]

    def review(self, actor_name, target_id, action):
        if action not in {"approve", "reject", "revoke"}:
            raise ValueError("不支持的审批操作。")
        with self.connection(write=True) as conn:
            actor = conn.execute("""SELECT u.id,a.role FROM users u
                JOIN astro_account_access a ON a.user_id=u.id WHERE u.username=?""", (actor_name,)).fetchone()
            if not actor or actor["role"] != "root":
                raise PermissionError("仅 root 可以管理管理员权限。")
            target = conn.execute("SELECT * FROM astro_account_access WHERE user_id=?", (target_id,)).fetchone()
            if not target:
                raise LookupError("账号不存在。")
            if target["role"] == "root" or target_id == actor["id"]:
                raise PermissionError("不能通过审批接口变更 root。")
            if action in {"approve", "reject"} and target["review_state"] != "pending":
                raise ValueError("该申请已处理，请刷新页面。")
            if action == "revoke" and target["role"] != "admin":
                raise ValueError("该账号不是管理员。")
            role = "admin" if action == "approve" else "user"
            state = "approved" if action == "approve" else "rejected" if action == "reject" else "none"
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""UPDATE astro_account_access SET role=?,review_state=?,reviewed_by=?,reviewed_at=?
                WHERE user_id=?""", (role, state, actor["id"], now, target_id))
            conn.execute("INSERT INTO astro_account_audit(actor_id,target_id,action,created_at) VALUES (?,?,?,?)",
                         (actor["id"], target_id, action, now))


def validate_registration(username, account_type):
    errors = []
    if username.casefold() == "root":
        errors.append("root 为系统保留账号，请使用其他用户名。")
    if account_type not in {"user", "admin"}:
        errors.append("请选择普通用户或申请管理员。")
    return errors


def record_registration(auth_session, user_id, account_type):
    """Called inside the SAME transaction as native User creation."""
    from sqlalchemy import text
    if account_type not in {"user", "admin"}:
        raise ValueError("Invalid account type")
    auth_session.execute(text("""INSERT INTO astro_account_access
        (user_id,role,requested_role,review_state) VALUES (:id,'user',:requested,:state)"""),
        {"id": user_id, "requested": account_type,
         "state": "pending" if account_type == "admin" else "none"})
