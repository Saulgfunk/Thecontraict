import uuid
from datetime import datetime
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import OrganizationKind, OrgRole, WorkspaceKind, WorkspaceRole

_TIMEZONES = available_timezones()


def _check_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise ValueError(f"Unknown time zone: {value}")
    return value


def _check_country(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 2 or not value.isalpha():
        raise ValueError("Country must be an ISO 3166-1 alpha-2 code")
    return value.upper()


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    name: str | None
    timezone: str


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: OrganizationKind
    default_timezone: str = "UTC"
    default_country: str | None = None

    _tz = field_validator("default_timezone")(_check_timezone)
    _country = field_validator("default_country")(_check_country)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    default_timezone: str | None = None
    default_country: str | None = None

    _tz = field_validator("default_timezone")(_check_timezone)
    _country = field_validator("default_country")(_check_country)


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: OrganizationKind
    default_timezone: str
    default_country: str | None
    created_at: datetime


class MyOrganization(BaseModel):
    organization: OrganizationOut
    role: OrgRole


class MeOut(BaseModel):
    user: UserOut
    organizations: list[MyOrganization]


class OrgMemberCreate(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class OrgMemberUpdate(BaseModel):
    role: OrgRole


class OrgMemberOut(ORMModel):
    id: uuid.UUID
    user: UserOut
    role: OrgRole
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: WorkspaceKind
    parent_workspace_id: uuid.UUID | None = None
    country: str | None = None
    timezone: str | None = None

    _tz = field_validator("timezone")(_check_timezone)
    _country = field_validator("country")(_check_country)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    country: str | None = None
    timezone: str | None = None

    _tz = field_validator("timezone")(_check_timezone)
    _country = field_validator("country")(_check_country)


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    parent_workspace_id: uuid.UUID | None
    name: str
    kind: WorkspaceKind
    country: str | None
    timezone: str | None
    created_at: datetime


class WorkspaceWithRole(WorkspaceOut):
    my_role: WorkspaceRole


class WorkspaceMemberCreate(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.VIEWER


class WorkspaceMemberOut(ORMModel):
    id: uuid.UUID
    user: UserOut
    role: WorkspaceRole
    created_at: datetime


class AuditEventOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    data: dict[str, object]
    at: datetime
