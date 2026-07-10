"""Team email invitations: a signed, expiring invite token (JWT), accept, and set-password-on-accept
which adds the member to the team. The invite email is sent via the email worker (SCRUM-25).
"""
from __future__ import annotations

import time

import jwt

from app.core.config import get_settings
from app.modules.identity.rbac import Role
from app.modules.identity.security import hash_password
from app.modules.teams.service import TeamService

INVITE_TTL = 7 * 24 * 3600  # 7 days
_ALGO = "HS256"


class InviteError(Exception):
    pass


def create_invite(team_id: str, email: str, role: Role, *, ttl: int = INVITE_TTL) -> str:
    payload = {"team_id": team_id, "email": email.lower(), "role": role.value,
               "exp": int(time.time()) + ttl}
    return jwt.encode(payload, get_settings().session_secret, algorithm=_ALGO)


def accept_invite(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().session_secret, algorithms=[_ALGO])
    except jwt.PyJWTError as e:
        raise InviteError(str(e)) from e


async def set_invite_password(teams: TeamService, token: str, password: str) -> dict:
    """Accept the invite and provision the member. Returns the new member's credentials record."""
    data = accept_invite(token)
    await teams.add_member(data["team_id"], data["email"], Role(data["role"]))
    return {"email": data["email"], "team_id": data["team_id"],
            "password_hash": hash_password(password)}
