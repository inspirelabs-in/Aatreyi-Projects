"""CurrentUser provider + reusable authorization helpers.

There is no authentication yet. `get_current_user` is the SINGLE place that decides
who the caller is — today it returns a simulated user from the DB (defaulting to the
GrabOn Platform Admin, so existing "see everything" behavior is preserved). When
real auth is added later, only this provider changes; the permission helpers and all
routers stay the same.

Simulation (for testing both roles now):
    * default            → GrabOn Platform Admin (is_admin=True)
    * header X-User-Email → that seeded user (real is_admin from the DB)
    * header X-Org-Slug   → a normal (non-admin) user of that organization
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException

from tools.organizations import (
    get_default_admin_ctx,
    get_org_by_slug,
    get_user_ctx_by_email,
)


@dataclass
class CurrentUser:
    id: str | None
    organization_id: str | None
    org_slug: str | None
    is_admin: bool
    email: str | None = None
    name: str | None = None


async def get_current_user(
    x_user_email: str | None = Header(default=None),
    x_org_slug: str | None = Header(default=None),
) -> CurrentUser:
    """Resolve the simulated current user. Replace this body with real auth later."""
    ctx: dict | None = None
    if x_user_email:
        ctx = await get_user_ctx_by_email(x_user_email.strip())
    elif x_org_slug:
        org = await get_org_by_slug(x_org_slug.strip())
        if org:
            # Simulate a NORMAL member of that organization (never admin).
            ctx = {"id": None, "name": f"Simulated {org['slug']} user", "email": None,
                   "organization_id": org["id"], "org_slug": org["slug"], "is_admin": False}
    if ctx is None:
        ctx = await get_default_admin_ctx()
    if ctx is None:
        # Fresh DB before the seed migration ran: fall back to a platform admin so
        # the app keeps working (identical to the pre-tenancy behavior).
        return CurrentUser(id=None, organization_id=None, org_slug="grabon", is_admin=True)
    return CurrentUser(
        id=ctx.get("id"), organization_id=ctx.get("organization_id"),
        org_slug=ctx.get("org_slug"), is_admin=bool(ctx.get("is_admin")),
        email=ctx.get("email"), name=ctx.get("name"),
    )


# ── reusable permission helpers (no duplicated logic in routers) ─────────────
def is_platform_admin(user: CurrentUser) -> bool:
    # Only GrabOn users can ever be admins (enforced at write time), so is_admin
    # is sufficient here.
    return bool(user.is_admin)


def can_access_channel(user: CurrentUser, channel) -> bool:
    # Per-user ownership: a normal user may only see channels they own. The GrabOn
    # Platform Admin sees/monitors every channel.
    if is_platform_admin(user):
        return True
    owner = getattr(channel, "owner_user_id", None)
    return owner is not None and str(owner) == str(user.id)


def can_manage_channel(user: CurrentUser, channel) -> bool:
    return can_access_channel(user, channel)


def can_manage_organization(user: CurrentUser, org_id: str) -> bool:
    return is_platform_admin(user) or str(org_id) == str(user.organization_id)


def can_edit_settings(user: CurrentUser, org_id: str) -> bool:
    return can_manage_organization(user, org_id)


def require(condition: bool, detail: str = "forbidden") -> None:
    """Raise 403 unless the permission condition holds."""
    if not condition:
        raise HTTPException(status_code=403, detail=detail)
