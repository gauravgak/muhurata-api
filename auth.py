"""
auth.py — verify Supabase-issued JWTs and gate endpoints.

The frontend signs users in with Supabase Auth (Google). Supabase hands
the browser an access token (a JWT). The browser sends it as
`Authorization: Bearer <token>` on calls that need identity. We verify
that token locally — no network call to Supabase on the hot path — using
either:

  - the project's JWKS endpoint (asymmetric keys, preferred), or
  - the legacy shared HS256 secret (SUPABASE_JWT_SECRET).

Dependencies:
  require_user   -> 401 unless a valid token is present. Returns {id, email}.
  require_admin  -> require_user + email must be in ADMIN_EMAILS, else 403.
  optional_user  -> returns {id, email} or None; never raises. For endpoints
                    that behave differently when signed in but don't require it.
"""

import os
import time

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import InvalidTokenError, PyJWKClient

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_JWKS_URL = os.environ.get("SUPABASE_JWKS_URL", "").strip()
if not SUPABASE_JWKS_URL and SUPABASE_URL:
    SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
_AUDIENCE = os.environ.get("SUPABASE_JWT_AUD", "authenticated").strip()
# Supabase signs from <project>/auth/v1 . Verified when SUPABASE_URL is set.
_ISSUER = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None
# New Supabase projects sign with ES256 (P-256). Older shared-secret
# projects use HS256; some use EdDSA. Accept the asymmetric set here.
_ASYM_ALGS = ["ES256", "RS256", "EdDSA"]

ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
}

# DEV ONLY. When set, every require_user / optional_user resolves to this
# email with no token — so the whole app can be exercised locally without
# a real Supabase project. NEVER set this in production (Render); there is
# no code path that sets it for you.
DEV_AUTH_EMAIL = os.environ.get("DEV_AUTH_EMAIL", "").strip().lower()
if DEV_AUTH_EMAIL:
    import sys as _sys
    print(f"[auth] WARNING: DEV_AUTH_EMAIL={DEV_AUTH_EMAIL!r} — sign-in is "
          f"BYPASSED. Local development only.", file=_sys.stderr)

# PyJWKClient keeps its own small cache; wrap it so a transient JWKS
# fetch failure doesn't wedge every request permanently.
_jwk_client = PyJWKClient(SUPABASE_JWKS_URL) if SUPABASE_JWKS_URL else None
_jwks_cooldown_until = 0.0


def configured() -> bool:
    return bool(_jwk_client or SUPABASE_JWT_SECRET)


def _decode(token: str) -> dict:
    global _jwks_cooldown_until
    last_err = None

    if _jwk_client and time.time() >= _jwks_cooldown_until:
        try:
            key = _jwk_client.get_signing_key_from_jwt(token).key
            kw = {"algorithms": _ASYM_ALGS, "audience": _AUDIENCE,
                  "options": {"verify_aud": True}}
            if _ISSUER:
                kw["issuer"] = _ISSUER
            return jwt.decode(token, key, **kw)
        except InvalidTokenError as e:
            last_err = e
        except Exception as e:  # network / JWKS parse — back off, try secret
            last_err = e
            _jwks_cooldown_until = time.time() + 30

    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token, SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=_AUDIENCE,
                options={"verify_aud": True},
            )
        except InvalidTokenError as e:
            last_err = e

    raise HTTPException(401, "Invalid or expired sign-in. Please sign in again.")


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if h[:7].lower() == "bearer ":
        return h[7:].strip() or None
    return None


def optional_user(request: Request) -> dict | None:
    if DEV_AUTH_EMAIL:
        return {"id": "dev-user", "email": DEV_AUTH_EMAIL}
    tok = _bearer(request)
    if not tok:
        return None
    try:
        claims = _decode(tok)
    except HTTPException:
        return None
    return {"id": claims.get("sub"), "email": (claims.get("email") or "").lower()}


def require_user(request: Request) -> dict:
    if DEV_AUTH_EMAIL:
        return {"id": "dev-user", "email": DEV_AUTH_EMAIL}
    tok = _bearer(request)
    if not tok:
        raise HTTPException(401, "Please sign in to continue.")
    claims = _decode(tok)
    uid = claims.get("sub")
    if not uid:
        raise HTTPException(401, "Sign-in token is missing a user id.")
    return {"id": uid, "email": (claims.get("email") or "").lower()}


def require_admin(user: dict = Depends(require_user)) -> dict:
    if not ADMIN_EMAILS:
        raise HTTPException(403, "Admin access is not configured.")
    if user["email"] not in ADMIN_EMAILS:
        raise HTTPException(403, "Not authorised.")
    return user
