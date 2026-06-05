from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from ..config import settings


def _extract_ops_token(*, x_ops_admin_token: str | None, authorization: str | None) -> str:
    if x_ops_admin_token:
        return x_ops_admin_token.strip()
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


def require_ops_admin_access(
    x_ops_admin_token: str | None = Header(default=None, alias="X-Ops-Admin-Token"),
    authorization: str | None = Header(default=None),
) -> None:
    configured_token = settings.ops_admin_token.strip()
    if not configured_token:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPS_ADMIN_TOKEN é obrigatório para endpoints /ops mutáveis em produção.",
            )
        return

    provided_token = _extract_ops_token(
        x_ops_admin_token=x_ops_admin_token,
        authorization=authorization,
    )
    if not provided_token or not secrets.compare_digest(provided_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token administrativo ausente ou inválido para endpoint operacional.",
            headers={"WWW-Authenticate": "Bearer"},
        )
