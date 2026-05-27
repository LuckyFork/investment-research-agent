import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    owner_user_id: str
    filename: str
    file_type: str
    file_size: int
    status: Literal["pending", "processing", "ready", "failed"]
    chunk_count: int
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    message: str


class DocumentListItem(BaseModel):
    id: uuid.UUID
    tenant_id: str
    owner_user_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]
    total: int
    page: int
    size: int
