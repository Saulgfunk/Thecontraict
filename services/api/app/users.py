from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_or_invite_user(db: Session, email: str) -> User:
    """Find a user by email, or create a placeholder that is linked to a login when the
    person first signs in with that email."""
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()
    return user
