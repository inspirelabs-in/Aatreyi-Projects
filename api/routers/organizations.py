"""Organization, current-user and organization-settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.authz import (
    CurrentUser,
    can_edit_settings,
    can_manage_organization,
    get_current_user,
    is_platform_admin,
    require,
)
from api.schemas import CreateOrganization, CreateUser, OrgSettingsUpdate
from tools.organizations import (
    create_organization,
    create_user,
    get_org_by_id,
    get_org_by_slug,
    get_settings,
    list_organizations,
    list_users,
    upsert_settings,
)

router = APIRouter(prefix="/api", tags=["organizations"])


@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    """The simulated logged-in user (default = GrabOn Platform Admin)."""
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "organization_id": current_user.organization_id,
        "org_slug": current_user.org_slug,
        "is_admin": current_user.is_admin,
        "is_platform_admin": is_platform_admin(current_user),
    }


@router.get("/organizations")
async def organizations(current_user: CurrentUser = Depends(get_current_user)):
    """Platform Admin sees every organization; a normal user sees only their own."""
    orgs = await list_organizations()
    if not is_platform_admin(current_user):
        orgs = [o for o in orgs if o["id"] == str(current_user.organization_id)]
    return orgs


async def _resolve_org_id(current_user: CurrentUser, organization_id: str | None) -> str:
    """Pick which org's settings to act on: the caller's own by default; a Platform
    Admin may target another via ?organization_id."""
    if organization_id and is_platform_admin(current_user):
        return organization_id
    if not current_user.organization_id:
        # Fallback (fresh DB / admin-without-org): resolve GrabOn.
        grab = await get_org_by_slug("grabon")
        if grab:
            return grab["id"]
        raise HTTPException(status_code=404, detail="organization not found")
    return str(current_user.organization_id)


@router.get("/settings")
async def get_org_settings(organization_id: str | None = Query(default=None),
                           current_user: CurrentUser = Depends(get_current_user)):
    org_id = await _resolve_org_id(current_user, organization_id)
    require(can_edit_settings(current_user, org_id), "not your organization's settings")
    s = await get_settings(org_id)
    if s is None:
        # No row yet → create defaults on first read so the UI always has values.
        s = await upsert_settings(org_id)
    return s


@router.patch("/settings")
async def patch_org_settings(body: OrgSettingsUpdate,
                             organization_id: str | None = Query(default=None),
                             current_user: CurrentUser = Depends(get_current_user)):
    org_id = await _resolve_org_id(current_user, organization_id)
    require(can_edit_settings(current_user, org_id), "not allowed to edit these settings")
    return await upsert_settings(
        org_id,
        auto_approve_content=body.auto_approve_content,
        daily_target_posts=body.daily_target_posts,
    )


# ── Organization CRUD ─────────────────────────────────────────────────────────
@router.post("/organizations", status_code=201)
async def create_org(body: CreateOrganization,
                     current_user: CurrentUser = Depends(get_current_user)):
    """Create a new organization — Platform Admin only."""
    require(is_platform_admin(current_user), "only platform admin can create organizations")
    try:
        return await create_organization(body.name, body.slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── User management ───────────────────────────────────────────────────────────
@router.get("/organizations/{org_id}/users")
async def list_org_users(org_id: str,
                         current_user: CurrentUser = Depends(get_current_user)):
    """List users within an organization. Platform Admin sees all; normal users see only their own."""
    require(can_manage_organization(current_user, org_id), "not your organization")
    return await list_users(org_id)


@router.post("/organizations/{org_id}/users", status_code=201)
async def create_org_user(org_id: str, body: CreateUser,
                          current_user: CurrentUser = Depends(get_current_user)):
    """Create a user within an organization."""
    require(can_manage_organization(current_user, org_id), "not your organization")
    org = await get_org_by_id(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    try:
        return await create_user(org["slug"], body.name, body.email, body.is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
