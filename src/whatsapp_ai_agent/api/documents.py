from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.db.repositories import ManagedDocumentRepository
from whatsapp_ai_agent.db.session import get_db_session
from whatsapp_ai_agent.documents.automation import (
    apply_table_update_to_document,
    automation_catalog,
    create_managed_table_document,
    document_summary_from_model,
    store_uploaded_document,
)
from whatsapp_ai_agent.documents.schemas import (
    DocumentationAutomationIdea,
    DocumentAutomationResult,
    DocumentKind,
    DocumentTableUpdateRequest,
    ManagedDocumentSummary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard-documents"])


class DocumentListResponse(BaseModel):
    documents: list[ManagedDocumentSummary]


class CreateTableDocumentRequest(BaseModel):
    org_id: UUID
    owner_user_id: UUID | None = None
    title: str = "Documentation Log"
    document_kind: DocumentKind = "xlsx"
    sheet_name: str | None = None
    key_columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, object]] = Field(default_factory=list)


@router.get("/documents", response_model=DocumentListResponse)
def list_dashboard_documents(
    org_id: UUID,
    query: str | None = None,
    document_kind: str | None = None,
    source_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    db_session: Session = Depends(get_db_session),
) -> DocumentListResponse:
    documents = ManagedDocumentRepository(db_session).list_documents(
        org_id=org_id,
        query=query,
        document_kind=document_kind,
        source_type=source_type,
        limit=limit,
    )
    return DocumentListResponse(documents=[document_summary_from_model(item) for item in documents])


@router.get("/documents/{document_id}", response_model=ManagedDocumentSummary)
def get_dashboard_document(
    document_id: UUID,
    org_id: UUID,
    db_session: Session = Depends(get_db_session),
) -> ManagedDocumentSummary:
    document = ManagedDocumentRepository(db_session).get(org_id=org_id, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document_summary_from_model(document)


@router.post("/documents/upload", response_model=ManagedDocumentSummary)
async def upload_dashboard_document(
    org_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    owner_user_id: Annotated[UUID | None, Form()] = None,
    display_name: Annotated[str | None, Form()] = None,
    summary: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    db_session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ManagedDocumentSummary:
    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    tag_list = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    registration = store_uploaded_document(
        org_id=org_id,
        owner_user_id=owner_user_id,
        filename=file.filename or "document",
        data=data,
        content_type=file.content_type,
        display_name=display_name,
        summary=summary,
        tags=tag_list,
        db_session=db_session,
        settings=settings,
    )
    db_session.commit()
    return document_summary_from_model(registration.document)


@router.post("/documents/create-table", response_model=DocumentAutomationResult)
def create_dashboard_table_document(
    request: CreateTableDocumentRequest,
    db_session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DocumentAutomationResult:
    update_request = DocumentTableUpdateRequest(
        instruction=f"Create {request.title}",
        target_document=request.title,
        document_kind=request.document_kind,
        sheet_name=request.sheet_name,
        table_name=request.title,
        key_columns=request.key_columns,
        rows=request.rows,
        create_if_missing=True,
    )
    result = create_managed_table_document(
        org_id=request.org_id,
        owner_user_id=request.owner_user_id,
        request=update_request,
        db_session=db_session,
        settings=settings,
    )
    db_session.commit()
    return result


@router.post("/documents/{document_id}/table-update", response_model=DocumentAutomationResult)
def update_dashboard_table_document(
    document_id: UUID,
    org_id: UUID,
    request: DocumentTableUpdateRequest,
    user_id: UUID | None = None,
    db_session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DocumentAutomationResult:
    repo = ManagedDocumentRepository(db_session)
    document = repo.get(org_id=org_id, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        result = apply_table_update_to_document(
            document=document,
            request=request,
            user_id=user_id,
            db_session=db_session,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db_session.commit()
    return result


@router.get("/documentation-ideas", response_model=list[DocumentationAutomationIdea])
def list_documentation_automation_ideas(
    industry: str | None = None,
) -> list[DocumentationAutomationIdea]:
    return automation_catalog(industry)
