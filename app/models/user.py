# kassensystem_basic/app/models/user.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint

from app.models.base import Base

# Rollen (Strings, konsistent mit main.py und RBAC)
ROLE_OWNER = "Owner"
ROLE_ADMIN = "Admin"
ROLE_MITARBEITER = "Mitarbeiter"
ROLE_BUCHHALTUNG = "Buchhaltung"
ROLE_GAST = "Gast"

VALID_ROLES = {ROLE_OWNER, ROLE_ADMIN, ROLE_MITARBEITER, ROLE_BUCHHALTUNG, ROLE_GAST}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default=ROLE_MITARBEITER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def has_role(self, *roles: str) -> bool:
        return self.role in roles
