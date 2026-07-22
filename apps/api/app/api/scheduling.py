"""Scheduling API — killzone / session status."""


from fastapi import APIRouter

from app.engine.scheduling import session_status

router = APIRouter(prefix="/api/v1/schedule", tags=["scheduling"])


@router.get("/status")
def get_session_status():
    return session_status()


__all__ = ["router"]
