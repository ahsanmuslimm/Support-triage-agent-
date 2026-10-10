"""Conversation endpoints."""

from fastapi import APIRouter, HTTPException, Header
from typing import Optional, List

from ...models.conversation import ConversationModel, ConversationStatus

router = APIRouter()


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> ConversationModel:
    """Get conversation details.

    Args:
        conversation_id: Conversation ID
        tenant_id: Tenant ID

    Returns:
        ConversationModel
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # TODO: Fetch from database
    return ConversationModel(
        id=conversation_id,
        tenant_id=tenant_id,
        customer_id="unknown",
        channel_id="web_chat",
    )


@router.get("/conversations", response_model=List[ConversationModel])
async def list_conversations(
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[ConversationModel]:
    """List conversations for tenant.

    Args:
        tenant_id: Tenant ID
        status: Filter by status
        limit: Max results
        offset: Pagination offset

    Returns:
        List of conversations
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # TODO: Fetch from database with filters
    return []


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    status: Optional[ConversationStatus] = None,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> ConversationModel:
    """Update conversation status.

    Args:
        conversation_id: Conversation ID
        status: New status
        tenant_id: Tenant ID

    Returns:
        Updated ConversationModel
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")

    # TODO: Update in database
    return ConversationModel(
        id=conversation_id,
        tenant_id=tenant_id,
        customer_id="unknown",
        channel_id="web_chat",
        status=status or ConversationStatus.OPEN,
    )
