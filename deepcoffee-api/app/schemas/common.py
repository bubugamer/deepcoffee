from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime


class DependencyState(BaseModel):
    status: str
    detail: str | None = None


class DependencyHealthResponse(BaseModel):
    database: DependencyState
    model_gateway: DependencyState
    langfuse: DependencyState
    knowledge: DependencyState


class MessageResponse(BaseModel):
    message: str


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
