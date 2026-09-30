"""
Request body schemas for the SCVMUN Platform API.

Field names are camelCase to match the JSON the frontend actually sends
(see Frontend-API-Contract.md and Frontend/src/views/).
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    hash: str
    password: str


class VerifyHashesRequest(BaseModel):
    password: str


class GradeSubmissionRequest(BaseModel):
    delegateId: int
    scores: dict[str, float]
    totalScore: str  # "<earned>/<max>", e.g. "18/20"
    comments: str = ""


class AwardAssignmentRequest(BaseModel):
    delegateId: int
    assignedAward: str
    scores: dict[str, float]
    totalScore: float
