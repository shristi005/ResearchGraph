"""FastAPI dependencies: authenticated user + a DB session scoped to that user."""
from fastapi import Depends, Header, HTTPException

from app import config
from app.auth_tokens import AuthError, User, verify
from app.database.session import open_session


def current_user(authorization: str | None = Header(default=None)) -> User:
    if config.AUTH_DISABLED:
        return User(id=config.LOCAL_USER_ID, email="local@localhost")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please sign in.", headers={"WWW-Authenticate": "Bearer"})
    try:
        return verify(authorization.split(" ", 1)[1].strip())
    except AuthError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "Bearer"})


def scoped_db(user: User = Depends(current_user)):
    db = open_session(user.id)
    try:
        yield db
    finally:
        db.close()
