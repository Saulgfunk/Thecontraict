"""Authentication: resolve the caller to a ``User`` row.

In ``clerk`` mode we verify the Clerk session JWT. The Clerk session token must be
customised (Clerk dashboard → Sessions → Customize session token) to include::

    {"email": "{{user.primary_email_address}}", "name": "{{user.full_name}}"}

In ``dev`` mode the caller is identified by the ``X-Dev-User-Email`` header. This mode
is refused in production (see ``app.config``).
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    name: str | None = None


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_clerk_token(token: str, settings: Settings) -> Identity:
    try:
        signing_key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid token") from exc

    azp = claims.get("azp")
    if settings.clerk_authorized_parties and azp not in settings.clerk_authorized_parties:
        raise _unauthorized("Invalid token origin")
    email = claims.get("email")
    if not email:
        raise _unauthorized("Token is missing the email claim")
    return Identity(subject=claims["sub"], email=email.lower(), name=claims.get("name"))


def get_identity(
    authorization: str | None = Header(default=None),
    x_dev_user_email: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Identity:
    if settings.auth_mode == "dev":
        if not x_dev_user_email:
            raise _unauthorized("Missing X-Dev-User-Email header")
        email = x_dev_user_email.strip().lower()
        return Identity(subject=f"dev|{email}", email=email)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing bearer token")
    return verify_clerk_token(authorization[7:], settings)


def get_current_user(
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db)
) -> User:
    user = db.scalar(select(User).where(User.auth_subject == identity.subject))
    if user is None:
        # Users invited by email exist before they first sign in: link them.
        user = db.scalar(select(User).where(User.email == identity.email))
        if user is None:
            user = User(email=identity.email, name=identity.name)
            db.add(user)
        elif user.auth_subject is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email is linked to another login")
        user.auth_subject = identity.subject
        if identity.name and not user.name:
            user.name = identity.name
        db.commit()
    return user
