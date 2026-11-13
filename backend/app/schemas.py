"""Validated API input and output schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Priority = Literal["low", "normal", "high", "urgent"]
TaskState = Literal[
    "pending",
    "assigned",
    "running",
    "waiting",
    "completed",
    "failed",
    "reviewing",
    "rework_required",
    "approved",
    "cancelled",
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank")
        return value


class ProjectRead(ORMModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10_000)
    system_instructions: str = Field(default="", max_length=20_000)
    provider: str = Field(default="unconfigured", min_length=1, max_length=64)
    model: str | None = Field(default=None, max_length=120)

    @field_validator("name", "role")
    @classmethod
    def required_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class AgentRead(ORMModel):
    id: str
    name: str
    role: str
    description: str
    system_instructions: str
    provider: str
    model: str | None
    status: str
    is_manager: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    priority: Priority = "normal"
    assigned_agent_id: str | None = None
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Task title cannot be blank")
        return value


class TaskRead(ORMModel):
    id: str
    project_id: str | None
    title: str
    description: str
    priority: str
    state: str
    assigned_agent_id: str | None
    dependencies: list[str]
    acceptance_criteria: list[str]
    retry_count: int
    output: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskAssignment(BaseModel):
    assigned_agent_id: str | None


class AuditEventRead(ORMModel):
    id: str
    entity_type: str
    entity_id: str | None
    event_type: str
    summary: str
    created_at: datetime
