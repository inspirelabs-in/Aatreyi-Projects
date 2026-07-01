"""Multi-tenancy helpers: organizations, users and organization settings.

Thin async DB helpers over the Organization / User / OrganizationSettings models.
Business rules that must not be trusted to the client live here — notably the
"only GrabOn users may be admins" rule (``create_user``). Returns plain dicts so
callers never hold detached ORM instances.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from db.base import AsyncSessionLocal
from db.models import Channel, Organization, OrganizationSettings, User

GRABON_SLUG = "grabon"


def _org_dict(o: Organization) -> dict[str, Any]:
    return {"id": str(o.id), "name": o.name, "slug": o.slug}


def _user_ctx(u: User, org: Organization) -> dict[str, Any]:
    return {
        "id": str(u.id), "name": u.name, "email": u.email,
        "organization_id": str(u.organization_id), "org_slug": org.slug,
        "is_admin": bool(u.is_admin),
    }


def _settings_dict(s: OrganizationSettings) -> dict[str, Any]:
    return {
        "id": str(s.id), "organization_id": str(s.organization_id),
        "auto_approve_content": bool(s.auto_approve_content),
        "daily_target_posts": s.daily_target_posts,
    }


# ── organizations ────────────────────────────────────────────────────────────
async def get_org_by_slug(slug: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as s:
        o = (await s.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
        return _org_dict(o) if o else None


async def get_grabon_org() -> dict[str, Any] | None:
    return await get_org_by_slug(GRABON_SLUG)


async def list_organizations() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Organization).order_by(Organization.name.asc()))).scalars().all()
        return [_org_dict(o) for o in rows]


# ── settings ─────────────────────────────────────────────────────────────────
async def get_settings(org_id: str | uuid.UUID) -> dict[str, Any] | None:
    oid = uuid.UUID(str(org_id))
    async with AsyncSessionLocal() as s:
        row = (await s.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == oid)
        )).scalar_one_or_none()
        return _settings_dict(row) if row else None


async def upsert_settings(org_id: str | uuid.UUID, **fields: Any) -> dict[str, Any]:
    """Create or update the org's settings row; only known fields are applied."""
    oid = uuid.UUID(str(org_id))
    allowed = {"auto_approve_content", "daily_target_posts"}
    async with AsyncSessionLocal() as s:
        row = (await s.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == oid)
        )).scalar_one_or_none()
        if row is None:
            row = OrganizationSettings(organization_id=oid)
            s.add(row)
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(row, k, v)
        await s.commit()
        await s.refresh(row)
        return _settings_dict(row)


async def get_settings_for_channel(channel_id: str | uuid.UUID) -> dict[str, Any] | None:
    """Resolve a channel → its organization → that org's settings (or None)."""
    cid = uuid.UUID(str(channel_id))
    async with AsyncSessionLocal() as s:
        org_id = (await s.execute(
            select(Channel.organization_id).where(Channel.id == cid)
        )).scalar_one_or_none()
        if org_id is None:
            return None
        row = (await s.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )).scalar_one_or_none()
        return _settings_dict(row) if row else None


# ── users ────────────────────────────────────────────────────────────────────
async def get_user_ctx_by_email(email: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not u:
            return None
        org = (await s.execute(select(Organization).where(Organization.id == u.organization_id))).scalar_one()
        return _user_ctx(u, org)


async def get_default_admin_ctx() -> dict[str, Any] | None:
    """The GrabOn Platform Admin — the default simulated user until real auth."""
    async with AsyncSessionLocal() as s:
        org = (await s.execute(select(Organization).where(Organization.slug == GRABON_SLUG))).scalar_one_or_none()
        if not org:
            return None
        u = (await s.execute(
            select(User).where(User.organization_id == org.id, User.is_admin.is_(True))
            .order_by(User.created_at.asc())
        )).scalars().first()
        return _user_ctx(u, org) if u else None


async def get_org_by_id(org_id: str | uuid.UUID) -> dict[str, Any] | None:
    oid = uuid.UUID(str(org_id))
    async with AsyncSessionLocal() as s:
        o = (await s.execute(select(Organization).where(Organization.id == oid))).scalar_one_or_none()
        return _org_dict(o) if o else None


async def create_organization(name: str, slug: str | None = None) -> dict[str, Any]:
    """Create a new organization with default settings. Generates slug from name if not provided."""
    import re
    async with AsyncSessionLocal() as s:
        if slug is None:
            slug = re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))[:64] or "org"
        existing = (await s.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
        if existing:
            raise ValueError(f"organization with slug '{slug}' already exists")
        org = Organization(name=name, slug=slug)
        s.add(org)
        await s.flush()
        s.add(OrganizationSettings(organization_id=org.id))
        await s.commit()
        await s.refresh(org)
        return _org_dict(org)


async def list_users(org_id: str | uuid.UUID) -> list[dict[str, Any]]:
    oid = uuid.UUID(str(org_id))
    async with AsyncSessionLocal() as s:
        org = (await s.execute(select(Organization).where(Organization.id == oid))).scalar_one_or_none()
        if not org:
            return []
        rows = (await s.execute(
            select(User).where(User.organization_id == oid).order_by(User.created_at.asc())
        )).scalars().all()
        return [_user_ctx(u, org) for u in rows]


async def create_user(org_slug: str, name: str, email: str | None, is_admin: bool = False) -> dict[str, Any]:
    """Create a user. ENFORCES the rule: only GrabOn-org users may be admins —
    any non-GrabOn user is forced to is_admin=False regardless of the request."""
    async with AsyncSessionLocal() as s:
        org = (await s.execute(select(Organization).where(Organization.slug == org_slug))).scalar_one_or_none()
        if org is None:
            raise ValueError(f"organization not found: {org_slug}")
        effective_admin = bool(is_admin) and org.slug == GRABON_SLUG
        u = User(name=name, email=email, organization_id=org.id, is_admin=effective_admin)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return _user_ctx(u, org)
