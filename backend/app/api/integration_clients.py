"""
MODULE: Integration access - who may hold a read-only key.

A key lets an external system read approved data (see app/api/integration.py). Separation of duties:
  - a BOT analyst CREATES a key (this role already reads all approved data, so no new power appears);
  - the System Administrator may NOT create one (that role may not read supervisory data, and a key would be a
    way round that rule) but may LIST keys and REVOKE any of them, as an emergency control;
  - an institution user has no access here at all.
The key is returned once, at creation. It is never stored, listed or written to the audit log.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.integration_auth import generate_api_key
from app.models.models import ApiClient, RoleEnum, User
from app.schemas.schemas import ApiClientCreate, ApiClientCreated, ApiClientOut
from app.services.audit_service import record_audit

router = APIRouter(prefix="/integration-clients", tags=["Integration access"])


def _status(client: ApiClient) -> str:
    if client.revoked_at is not None:
        return "REVOKED"
    if client.expires_at <= datetime.utcnow():
        return "EXPIRED"
    return "ACTIVE"


def _out(client: ApiClient) -> dict:
    return dict(
        id=client.id, name=client.name, description=client.description, key_prefix=client.key_prefix, scope=client.scope, allowed_networks=client.allowed_networks,
        status=_status(client),
        created_by_username=client.created_by.username if client.created_by else None,
        revoked_by_username=client.revoked_by.username if client.revoked_by else None,
        created_at=client.created_at, expires_at=client.expires_at,
        last_used_at=client.last_used_at, revoked_at=client.revoked_at,
    )


@router.post("", response_model=ApiClientCreated, status_code=status.HTTP_201_CREATED)
def create_api_client(
    payload: ApiClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER)),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the key a name that says which system it is for")
    taken = db.query(ApiClient).filter(func.lower(ApiClient.name) == name.lower(), ApiClient.revoked_at.is_(None)).first()
    if taken:
        raise HTTPException(status_code=409, detail="A live key with this name already exists; revoke it first or choose another name")

    now = datetime.utcnow()
    client = None
    for _ in range(3):   # a clash of the 40-bit public prefix is vanishingly rare; retry rather than fail
        key, prefix, key_hash = generate_api_key()
        client = ApiClient(
            name=name, description=(payload.description or "").strip() or None,
            key_prefix=prefix, key_hash=key_hash, scope=payload.scope, allowed_networks=payload.allowed_networks, created_by_user_id=current_user.id,
            created_at=now, expires_at=now + timedelta(days=payload.valid_days),
        )
        db.add(client)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            client = None
    if client is None:
        raise HTTPException(status_code=409, detail="Could not create the key; try again")
    db.refresh(client)

    record_audit(
        db, current_user.id, "INTEGRATION_CLIENT_CREATED", "ApiClient", client.id,
        f"{client.scope} key '{client.name}' created, valid {payload.valid_days} days",
        details_json={"key_prefix": client.key_prefix, "valid_days": payload.valid_days, "scope": client.scope, "allowed_networks": client.allowed_networks},
    )
    return ApiClientCreated(**_out(client), api_key=key)


@router.get("", response_model=list[ApiClientOut])
def list_api_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)),
):
    clients = db.query(ApiClient).order_by(ApiClient.created_at.desc()).all()
    return [_out(c) for c in clients]


@router.post("/{client_id}/revoke", response_model=ApiClientOut)
def revoke_api_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN)),
):
    client = db.query(ApiClient).filter(ApiClient.id == client_id).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Key not found")
    if client.revoked_at is not None:
        raise HTTPException(status_code=409, detail="This key is already revoked")
    client.revoked_at = datetime.utcnow()
    client.revoked_by_user_id = current_user.id
    db.commit()
    db.refresh(client)
    record_audit(
        db, current_user.id, "INTEGRATION_CLIENT_REVOKED", "ApiClient", client.id,
        f"{client.scope} key '{client.name}' revoked", details_json={"key_prefix": client.key_prefix, "scope": client.scope},
    )
    return _out(client)
