# kassensystem_basic/app/services/auth.py
import base64
import hmac
import os
from hashlib import pbkdf2_hmac
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.user import (
    User,
    ROLE_ADMIN,
    ROLE_OWNER,
)

# Session Keys
SESSION_USER_ID = "user_id"
SESSION_ROLE = "role"

# ---------- Passwort-Hashing (PBKDF2) ----------
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))

def hash_password(plain: str, *, iterations: int = 310_000, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${_b64(salt)}${_b64(dk)}"

def verify_password(plain: str, stored: str) -> bool:
    try:
        scheme, s_iter, s_salt, s_hash = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        iterations = int(s_iter)
        salt = _unb64(s_salt)
        expected = _unb64(s_hash)
        test = pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(test, expected)
    except Exception:
        return False

# ---------- Auth-Helpers ----------
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email, User.is_active == True).first()  # noqa: E712
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_ID] = user.id
    request.session[SESSION_ROLE] = user.role

def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_ID, None)
    request.session.pop(SESSION_ROLE, None)

def get_current_user(request: Request, db: Session) -> Optional[User]:
    uid = request.session.get(SESSION_USER_ID)
    if not uid:
        return None
    return db.query(User).filter(User.id == uid, User.is_active == True).first()  # noqa: E712

def is_admin_or_owner(request: Request) -> bool:
    return request.session.get(SESSION_ROLE) in {ROLE_ADMIN, ROLE_OWNER}

# ---------- Seeds ----------
def seed_users_if_empty(db: Session) -> None:
    """Legt Demo-Benutzer an, falls Tabelle leer ist."""
    if db.query(User).count() > 0:
        return
    seeds = [
        ("owner@example.com", "Owner Demo", "owner1234", "Owner"),
        ("admin@example.com", "Admin Demo", "admin1234", "Admin"),
        ("buchhaltung@example.com", "Buchhaltung Demo", "buch1234", "Buchhaltung"),
        ("mitarbeiter@example.com", "Mitarbeiter Demo", "mitarbeiter1234", "Mitarbeiter"),
        ("gast@example.com", "Gast Demo", "gast1234", "Gast"),
    ]
    for email, name, pw, role in seeds:
        db.add(User(email=email, full_name=name, password_hash=hash_password(pw), role=role, is_active=True))
    db.commit()
