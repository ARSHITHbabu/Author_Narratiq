"""
Authentication and session management.

Stage 10 (task 10.7, decisions S10-E/S10-F) — browser sessions:

  * The JWT is set as an HttpOnly cookie (`narratiq_session`) on sign-in and is
    NEVER returned in a response body, so no page script can read it. The
    frontend reaches this API through its own origin (Next.js rewrites
    /api/* to the backend), which makes the cookie first-party.
  * CSRF: double-submit token — a readable `narratiq_csrf` cookie that the
    frontend echoes in `X-CSRF-Token` on every state-changing request
    (middleware/csrf.py enforces it for cookie-authenticated requests).
  * The `Authorization: Bearer` header is still accepted, for API tooling and
    the test suite. A browser never sends one.

Session semantics (explicit, tested in test_sessions_stage10.py):

  * Every token carries `jti` (unique per sign-in), `ver` (the account's
    token_version at sign-in), `iat`, `exp`, `sub`.
  * POST /logout        — ends THIS session only: its jti is recorded in
                          revoked_sessions until the token would have expired.
                          Other devices stay signed in.
  * POST /change-password — bumps token_version: every existing session of the
                          account ends; the device that changed the password
                          receives a fresh session and stays signed in.
  * DELETE /account     — bumps token_version and deletes the account
                          (services/account_deletion.py): every session ends.
  * A token without `jti`/`ver` (issued before Stage 10) is refused: one
    re-sign-in, no silent acceptance of an unrevocable token.

The voice WebSocket connects to the backend directly (Next.js does not proxy
long-lived sockets reliably), where the session cookie is not sent. It
authenticates with a single-use ticket from POST /ws-ticket, valid for
`ws_ticket_ttl_seconds`, kept in process memory (valid under the single-worker
decision D-3, enforced by startup/worker_guard.py).
"""
import hmac
import logging
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from pydantic import BaseModel
import bcrypt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import RevokedSession, User
from schemas import SessionOut, UserCreate, UserLogin, UserOut
from middleware.rate_limit import get_remote_address, get_user_id, limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

MIN_NEW_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Tokens ────────────────────────────────────────────────────────────────────

def create_token(user_id: str, token_version: int = 0) -> str:
    now = datetime.utcnow()
    return jwt.encode(
        {
            "sub": user_id,
            "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
            "iat": now,
            "jti": uuid.uuid4().hex,
            "ver": int(token_version or 0),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_claims(token: str) -> dict:
    """Verified claims, or 401. Signature, algorithm and expiry are enforced."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return claims


def decode_token(token: str) -> str:
    return decode_claims(token)["sub"]


def _is_revoked(db: Session, jti: str) -> bool:
    return db.query(RevokedSession.jti).filter(RevokedSession.jti == jti).first() is not None


def user_for_token(token: str, db: Session) -> tuple[User, dict]:
    """The account a token belongs to, after every session check. 401 otherwise."""
    claims = decode_claims(token)
    jti, ver = claims.get("jti"), claims.get("ver")
    if not jti or not isinstance(ver, int):
        # Pre-Stage-10 token: it cannot be revoked individually, so it is not accepted.
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    user = db.query(User).filter(User.user_id == claims["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if ver != (user.token_version or 0) or _is_revoked(db, jti):
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    return user, claims


bearer = HTTPBearer(auto_error=False)


def _request_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(settings.session_cookie_name) or None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = _request_token(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user, claims = user_for_token(token, db)
    request.state.session_claims = claims
    return user


# ── Cookies ───────────────────────────────────────────────────────────────────

def _secure(request: Request) -> bool:
    mode = (settings.session_cookie_secure or "auto").strip().lower()
    if mode in ("true", "1", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def _set_session_cookies(response: Response, request: Request, token: str) -> None:
    secure = _secure(request)
    max_age = settings.jwt_expire_minutes * 60
    response.set_cookie(settings.session_cookie_name, token, max_age=max_age, path="/",
                        httponly=True, secure=secure, samesite="lax")
    # Readable on purpose: the frontend echoes it in X-CSRF-Token. Not a credential.
    response.set_cookie(settings.csrf_cookie_name, secrets.token_urlsafe(32), max_age=max_age,
                        path="/", httponly=False, secure=secure, samesite="lax")


def _clear_session_cookies(response: Response, request: Request) -> None:
    secure = _secure(request)
    for name, http_only in ((settings.session_cookie_name, True), (settings.csrf_cookie_name, False)):
        response.delete_cookie(name, path="/", secure=secure, httponly=http_only, samesite="lax")


def _start_session(response: Response, request: Request, user: User) -> SessionOut:
    _set_session_cookies(response, request, create_token(user.user_id, user.token_version or 0))
    return SessionOut(user=UserOut.model_validate(user))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=SessionOut)
@limiter.limit(settings.rate_limit_auth, key_func=get_remote_address)
def register(request: Request, response: Response, data: UserCreate, db: Session = Depends(get_db)):
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
    return _start_session(response, request, user)


@router.post("/login", response_model=SessionOut)
@limiter.limit(settings.rate_limit_auth, key_func=get_remote_address)
def login(request: Request, response: Response, data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        # No email in the log line: it is personal data (Stage 10 log review).
        logger.warning("[auth] failed login attempt")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("[auth] login: user=%s", user.user_id[:8])
    return _start_session(response, request, user)


@router.post("/logout", status_code=200)
def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    """End THIS session. Always clears the cookies and answers 200, so the
    browser can always sign out — even with an already-expired session. A
    valid session's jti is recorded so the token stops working everywhere it
    may have been copied. Other sessions of the same account are unaffected."""
    token = _request_token(request, credentials)
    if token:
        try:
            user, claims = user_for_token(token, db)
            if not _is_revoked(db, claims["jti"]):
                db.add(RevokedSession(
                    jti=claims["jti"], user_id=user.user_id,
                    expires_at=datetime.utcfromtimestamp(int(claims["exp"])),
                ))
                db.commit()
            logger.info("[auth] logout: user=%s", user.user_id[:8])
        except HTTPException:
            pass   # already invalid — nothing to revoke
    _clear_session_cookies(response, request)
    return {"logged_out": True}


@router.get("/me", response_model=UserOut)
def me(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    # A session that predates the CSRF cookie (or lost it) gets one here, so
    # its next state-changing request can pass the CSRF check.
    if request.cookies.get(settings.session_cookie_name) and not request.cookies.get(settings.csrf_cookie_name):
        response.set_cookie(settings.csrf_cookie_name, secrets.token_urlsafe(32),
                            max_age=settings.jwt_expire_minutes * 60, path="/", httponly=False,
                            secure=_secure(request), samesite="lax")
    return UserOut.model_validate(current_user)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=SessionOut)
@limiter.limit(settings.rate_limit_auth, key_func=get_user_id)
def change_password(
    request: Request,
    response: Response,
    data: ChangePasswordIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the password and end every OTHER session of the account. This
    device gets a fresh session so the author is not signed out mid-task."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Your current password is not correct.")
    if len(data.new_password) < MIN_NEW_PASSWORD_LENGTH:
        raise HTTPException(status_code=422,
                            detail=f"Choose a new password of at least {MIN_NEW_PASSWORD_LENGTH} characters.")
    if hmac.compare_digest(data.new_password, data.current_password):
        raise HTTPException(status_code=422, detail="The new password must differ from the current one.")
    current_user.hashed_password = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 0) + 1
    db.commit()
    db.refresh(current_user)
    logger.info("[auth] password changed; all sessions ended: user=%s", current_user.user_id[:8])
    return _start_session(response, request, current_user)


class DeleteAccountIn(BaseModel):
    password: str
    confirm: str   # must be exactly "DELETE" — typed by the author in the UI


@router.delete("/account")
@limiter.limit(settings.rate_limit_auth, key_func=get_user_id)
def delete_account(
    request: Request,
    response: Response,
    data: DeleteAccountIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the signed-in account and all of its data (task
    10.6, decision S10-G). Requires the password again and the typed word
    DELETE. Every session ends: the account no longer exists."""
    from services.account_deletion import delete_account as _delete
    if data.confirm != "DELETE":
        raise HTTPException(status_code=422, detail='Type DELETE to confirm that you want to delete your account.')
    if not verify_password(data.password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Your password is not correct. Nothing was deleted.")
    user_id = current_user.user_id
    db.expunge(current_user)
    try:
        result = _delete(db, user_id)
    except Exception as exc:                          # noqa: BLE001 — reported honestly, nothing deleted
        logger.error("[auth] account deletion failed, nothing deleted: user=%s (%s)", user_id[:8], type(exc).__name__)
        raise HTTPException(status_code=500, detail="Your account could not be deleted because of a problem "
                                                    "on our side. Nothing was deleted. Please try again later.")
    _clear_session_cookies(response, request)
    return {"deleted": True, "rows_deleted": sum(result["rows"].values()),
            "files_removed": result["files_removed"], "files_pending": result["files_pending"]}


# ── Voice WebSocket tickets ───────────────────────────────────────────────────

_ws_tickets: dict[str, tuple[str, float]] = {}   # ticket -> (user_id, monotonic expiry)
_ws_lock = threading.Lock()


def issue_ws_ticket(user_id: str) -> str:
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _ws_lock:
        for t, (_, exp) in list(_ws_tickets.items()):
            if exp <= now:
                del _ws_tickets[t]
        _ws_tickets[ticket] = (user_id, now + settings.ws_ticket_ttl_seconds)
    return ticket


def consume_ws_ticket(ticket: str | None) -> str | None:
    """The user id for a valid, unexpired ticket — which is then gone. None otherwise."""
    if not ticket:
        return None
    with _ws_lock:
        entry = _ws_tickets.pop(ticket, None)
    if entry is None or entry[1] <= time.monotonic():
        return None
    return entry[0]


@router.post("/ws-ticket")
def ws_ticket(current_user: User = Depends(get_current_user)):
    return {"ticket": issue_ws_ticket(current_user.user_id),
            "expires_in": settings.ws_ticket_ttl_seconds}
