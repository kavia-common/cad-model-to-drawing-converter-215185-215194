import os
from sqlalchemy.orm import Session as SASession
from sqlalchemy import select

from src.api.main import SessionLocal, User, hash_password


# PUBLIC_INTERFACE
def seed_admin(email: str = None, password: str = None) -> None:
    """
    Ensure an admin user exists. Uses ADMIN_EMAIL and ADMIN_PASSWORD env vars if not provided.
    If a user with the given email exists, no action is taken.

    Environment:
    - ADMIN_EMAIL
    - ADMIN_PASSWORD
    """
    email = email or os.getenv("ADMIN_EMAIL", "admin@example.com")
    password = password or os.getenv("ADMIN_PASSWORD", "Admin@12345")
    db: SASession = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            return
        u = User(email=email, password_hash=hash_password(password))
        db.add(u)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
