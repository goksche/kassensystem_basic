import base64
import hmac
import os
from hashlib import pbkdf2_hmac
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User, VALID_ROLES, ROLE_ADMIN


# Session Keys (kompatibel zur vorhandenen Session-Nutzung)
SESSION_USER_ID = "user_id"
SESSION_ROLE = "role"

# PBKDF2 Parameter
_PBKDF2_NAME = "pbkdf2_sha256"
_PBKDF2_ITERS = 260000  # sicher und flott genug
_SALT_LEN = 16


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def hash_password(plain: str) -> str:
    """Erzeugt Hash-String: 'pbkdf2_sha256$iters$salt$hash'"""
    salt = os.urandom(_SALT_LEN)
    dk = pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, _PBKDF2_ITERS)
    return f"{_PBKDF2_NAME}${_PBKDF2_ITERS}${_b64e(salt)}${_b64e(dk)}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        name, iters_s, salt_s, dk_s = hashed.split("$", 3)
        if name != _PBKDF2_NAME:
            return False
        iters = int(iters_s)
        salt = _b64d(salt_s)
        expected = _b64d(dk_s)
        got = pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iters)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email, User.is_active == True).first()  # noqa: E712
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def login_user(request, user: User) -> None:
    # fuer Kompatibilitaet: Rolle weiterhin auch separat in der Session
    request.session[SESSION_USER_ID] = user.id
    request.session[SESSION_ROLE] = user.role


def logout_user(request) -> None:
    request.session.pop(SESSION_USER_ID, None)
    request.session.pop(SESSION_ROLE, None)


def seed_demo_users(db: Session) -> None:
    """Legt noetige Demo-Benutzer an, wenn sie fehlen. Idempotent."""
    seeds = [
        ("owner@example.com", "Owner Demo", "owner1234", "Owner"),
        ("admin@example.com", "Admin Demo", "admin1234", "Admin"),
        ("buchhaltung@example.com", "Buchhaltung Demo", "buch1234", "Buchhaltung"),
        ("mitarbeiter@example.com", "Mitarbeiter Demo", "mitarbeiter1234", "Mitarbeiter"),
        ("gast@example.com", "Gast Demo", "gast1234", "Gast"),
    ]
    existing = {u.email for u in db.query(User).all()}
    created = False
    for email, name, pw, role in seeds:
        if email in existing:
            continue
        db.add(User(email=email, full_name=name, password_hash=hash_password(pw), role=role, is_active=True))
        created = True
    if created:
        db.commit()
