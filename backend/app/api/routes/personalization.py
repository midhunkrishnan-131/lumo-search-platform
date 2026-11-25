"""FastAPI routes for LUMO Phase 17: Adaptive Intelligence & Personalization Engine."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.personalization.service import PersonalizationService
from app.schemas.personalization import (
    FeedbackCreate,
    FeedbackResponse,
    PersonalizationProfileResponse,
    PersonalizationSettingsSchema,
    PersonalizationSettingsUpdate,
    PersonalizationStatusResponse,
    RecommendationItem,
    SourcePreferenceCreate,
    SourcePreferenceResponse,
    TopicProfileResponse,
    UserInterestCreate,
    UserInterestResponse,
)

router = APIRouter(prefix="/personalization", tags=["personalization"])


@router.get("/status", response_model=PersonalizationStatusResponse, summary="Personalization Status")
def get_personalization_status(db: Session = Depends(get_db)) -> PersonalizationStatusResponse:
    return PersonalizationService(db).get_status()


@router.get("/profile", response_model=PersonalizationProfileResponse, summary="Full Personalization Profile")
def get_personalization_profile(db: Session = Depends(get_db)) -> PersonalizationProfileResponse:
    return PersonalizationService(db).get_profile()


@router.put("/settings", response_model=PersonalizationSettingsSchema, summary="Update Personalization Settings")
def update_personalization_settings(
    payload: PersonalizationSettingsUpdate,
    db: Session = Depends(get_db),
) -> PersonalizationSettingsSchema:
    return PersonalizationService(db).update_settings(payload)


# --- Interests ---


@router.get("/interests", response_model=list[UserInterestResponse], summary="List User Interests")
def list_interests(db: Session = Depends(get_db)) -> list[UserInterestResponse]:
    return PersonalizationService(db).list_interests()


@router.post(
    "/interests",
    response_model=UserInterestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Explicit or Excluded Interest",
)
def add_interest(payload: UserInterestCreate, db: Session = Depends(get_db)) -> UserInterestResponse:
    try:
        return PersonalizationService(db).add_interest(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/interests/{interest_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Interest")
def delete_interest(interest_id: str, db: Session = Depends(get_db)) -> None:
    if not PersonalizationService(db).delete_interest(interest_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interest not found.")


# --- Topics ---


@router.get("/topics", response_model=list[TopicProfileResponse], summary="List Observed Topic Profiles")
def list_topics(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
) -> list[TopicProfileResponse]:
    return PersonalizationService(db).list_topics(limit=limit)


@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Topic Profile")
def delete_topic(topic_id: str, db: Session = Depends(get_db)) -> None:
    if not PersonalizationService(db).delete_topic(topic_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found.")


# --- Recommendations ---


@router.get("/recommendations", response_model=list[RecommendationItem], summary="Personalized Discovery Recommendations")
def get_recommendations(
    limit: Annotated[int, Query(ge=1, le=30)] = 12,
    db: Session = Depends(get_db),
) -> list[RecommendationItem]:
    return PersonalizationService(db).get_recommendations(limit=limit)


# --- Sources ---


@router.get("/sources", response_model=list[SourcePreferenceResponse], summary="List Source Preferences")
def list_sources(db: Session = Depends(get_db)) -> list[SourcePreferenceResponse]:
    return PersonalizationService(db).list_sources()


@router.post(
    "/sources",
    response_model=SourcePreferenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Preferred or Excluded Domain",
)
def add_source(payload: SourcePreferenceCreate, db: Session = Depends(get_db)) -> SourcePreferenceResponse:
    try:
        return PersonalizationService(db).add_source_preference(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Source Preference")
def delete_source(source_id: str, db: Session = Depends(get_db)) -> None:
    if not PersonalizationService(db).delete_source_preference(source_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source preference not found.")


# --- Feedback & Activity ---


@router.get("/activity", response_model=list[FeedbackResponse], summary="Recent Personalization Feedback & Activity")
def get_activity(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_db),
) -> list[FeedbackResponse]:
    return PersonalizationService(db).list_feedback(limit=limit)


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Optional Personalization Feedback",
)
def submit_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)) -> FeedbackResponse:
    return PersonalizationService(db).record_feedback(payload)


@router.delete("/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Feedback")
def delete_feedback(feedback_id: str, db: Session = Depends(get_db)) -> None:
    if not PersonalizationService(db).delete_feedback(feedback_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found.")


# --- Reset ---


@router.post("/reset", summary="Reset and Delete All Personalization Data")
def reset_personalization(db: Session = Depends(get_db)) -> dict[str, str]:
    PersonalizationService(db).reset_all()
    return {"status": "reset", "message": "All personalization profile data has been deleted and disabled."}
