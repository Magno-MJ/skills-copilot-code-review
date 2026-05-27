"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=400)
    starts_on: Optional[str] = None
    expires_on: str

    @field_validator("title", "message")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("starts_on", "expires_on")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if value in (None, ""):
            return None

        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Dates must use YYYY-MM-DD format") from error

        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "AnnouncementPayload":
        if self.starts_on and self.expires_on:
            if date.fromisoformat(self.starts_on) > date.fromisoformat(self.expires_on):
                raise ValueError("Start date cannot be after expiration date")

        return self


def ensure_authenticated_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": document.get("id") or document["_id"],
        "title": document["title"],
        "message": document["message"],
        "starts_on": document.get("starts_on"),
        "expires_on": document["expires_on"],
        "created_by": document.get("created_by")
    }


def is_active_announcement(document: Dict[str, Any], today: date) -> bool:
    starts_on = document.get("starts_on")
    expires_on = date.fromisoformat(document["expires_on"])

    if starts_on and date.fromisoformat(starts_on) > today:
        return False

    return expires_on >= today


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    today = date.today()
    documents = announcements_collection.find().sort("expires_on", 1)

    return [
        serialize_announcement(document)
        for document in documents
        if is_active_announcement(document, today)
    ]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    ensure_authenticated_user(teacher_username)

    documents = announcements_collection.find().sort([
        ("expires_on", 1),
        ("title", 1)
    ])

    return [serialize_announcement(document) for document in documents]


@router.post("", response_model=Dict[str, Any], status_code=201)
@router.post("/", response_model=Dict[str, Any], status_code=201)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    teacher = ensure_authenticated_user(teacher_username)

    announcement_id = uuid4().hex[:12]
    document = {
        "_id": announcement_id,
        "id": announcement_id,
        **payload.model_dump(),
        "created_by": teacher["username"]
    }

    announcements_collection.insert_one(document)
    return serialize_announcement(document)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    ensure_authenticated_user(teacher_username)

    existing_announcement = announcements_collection.find_one({"_id": announcement_id})
    if not existing_announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated_document = {
        **existing_announcement,
        **payload.model_dump()
    }

    announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": payload.model_dump()}
    )

    return serialize_announcement(updated_document)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    ensure_authenticated_user(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}