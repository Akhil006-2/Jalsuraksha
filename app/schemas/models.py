from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class Depth(str, Enum):
    ankle = "ankle"
    knee = "knee"
    waist_or_stalled_cars = "waist_or_stalled_cars"
    unknown = "unknown"

class Status(str, Enum):
    new = "new"
    corroborated = "corroborated"
    verified = "verified"
    resolved = "resolved"
    rejected = "rejected"

class Vehicle(str, Enum):
    pedestrian = "pedestrian"
    two_wheeler = "two_wheeler"
    sedan = "sedan"
    ambulance = "ambulance"
    emergency_vehicle = "emergency_vehicle"

class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class ReportCreate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    depth: Depth
    reporter_id: str = Field(min_length=1, max_length=128, description="Opaque app identifier; do not submit a real name.")
    description: str | None = Field(default=None, max_length=1000)
    photo_key: str | None = Field(default=None, max_length=512)
    observed_at: datetime | None = None

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        return value

class ReportUpdate(BaseModel):
    status: Status | None = None
    description: str | None = Field(default=None, max_length=1000)

class Report(BaseModel):
    id: str
    latitude: float
    longitude: float
    depth: Depth
    reporter_id: str
    description: str | None
    photo_key: str | None
    observed_at: datetime
    received_at: datetime
    status: Status

class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate
    vehicle: Vehicle = Vehicle.sedan
    alternatives: int = Field(default=3, ge=1, le=5)
    avoid_uncertain_hazards: bool = True
