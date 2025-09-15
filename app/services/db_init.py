from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.services.auth import hash_password


def seed_core_users(db: Session) -> None:
    """
    Legt initiale Benutzer an, falls nicht vorhanden.
    Passwoerter sind Demo-Passwoerter – bitte nach dem ersten Login aendern.
    """
    default_users = [
        {
            "email": "owner@example.com",
            "full_name": "Owner Demo",
            "role": UserRole.OWNER,
            "password": "owner1234",
        },
        {
            "email": "admin@example.com",
            "full_name": "Admin Demo",
            "role": UserRole.ADMIN,
            "password": "admin1234",
        },
        {
            "email": "buchhaltung@example.com",
            "full_name": "Buchhaltung Demo",
            "role": UserRole.BUCHHALTUNG,
            "password": "buch1234",
        },
        {
            "email": "mitarbeiter@example.com",
            "full_name": "Mitarbeiter Demo",
            "role": UserRole.MITARBEITER,
            "password": "mitarbeiter1234",
        },
        {
            "email": "gast@example.com",
            "full_name": "Gast Demo",
            "role": UserRole.GAST,
            "password": "gast1234",
        },
    ]

    for u in default_users:
        exists = db.query(User).filter(User.email == u["email"]).first()
        if not exists:
            db.add(
                User(
                    email=u["email"],
                    full_name=u["full_name"],
                    role=u["role"],
                    password_hash=hash_password(u["password"]),
                    is_active=True,
                )
            )
    db.commit()
