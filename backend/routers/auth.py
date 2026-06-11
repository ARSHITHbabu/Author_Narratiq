import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from jose import jwt
import bcrypt

from config import settings
from database import get_db
from models import User
from schemas import UserCreate, UserLogin, Token, UserOut
from middleware.rate_limit import limiter, get_remote_address

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(credentials.credentials)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register", response_model=Token)
@limiter.limit(settings.rate_limit_auth, key_func=get_remote_address)
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username taken")
    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("[auth] new user registered: %s", user.user_id[:8])
    token = create_token(user.user_id)
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_auth, key_func=get_remote_address)
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning("[auth] failed login attempt for email=%r", data.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("[auth] login: user=%s", user.user_id[:8])
    token = create_token(user.user_id)
    return Token(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


@router.post("/logout", status_code=200)
def logout(current_user: User = Depends(get_current_user)):
    """
    Explicit logout endpoint. Currently stateless (JWT tokens cannot be revoked
    without a token blacklist). Returns 200 to allow the frontend to always call
    this endpoint regardless of auth implementation. When a token blacklist is
    added (Phase B), this endpoint will invalidate the token server-side.
    """
    logger.info("[auth] logout: user=%s", current_user.user_id[:8])
    return {"logged_out": True}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
