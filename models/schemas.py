from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class UserRegister(BaseModel):
    email: str
    username: str
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Device schemas
# ---------------------------------------------------------------------------

DeviceType = Literal["ir_rgb", "ir_tv", "ir_ac", "relay", "wol"]


class DeviceCreate(BaseModel):
    name: str
    device_type: DeviceType
    room: Optional[str] = None
    room_id: Optional[int] = None
    mqtt_topic: str
    mac_address: Optional[str] = None
    ir_codes: Optional[dict] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    room: Optional[str] = None
    room_id: Optional[int] = None
    mqtt_topic: Optional[str] = None
    is_online: Optional[bool] = None
    last_status: Optional[str] = None
    mac_address: Optional[str] = None
    ir_codes: Optional[dict] = None


class DeviceResponse(BaseModel):
    id: int
    name: str
    device_type: str
    room: Optional[str] = None
    room_id: Optional[int] = None
    mqtt_topic: str
    is_online: bool
    last_status: Optional[str] = None
    mac_address: Optional[str] = None
    ir_codes: Optional[str] = None
    owner_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Room schemas
# ---------------------------------------------------------------------------


class RoomCreate(BaseModel):
    name: str
    icon: Optional[str] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None


class RoomResponse(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None
    device_count: int

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Scene schemas
# ---------------------------------------------------------------------------


class SceneActionCreate(BaseModel):
    device_id: int
    action: str
    value: Optional[str] = None
    order: int = 0
    delay_seconds: int = 0


class SceneCreate(BaseModel):
    name: str
    icon: Optional[str] = None
    actions: List[SceneActionCreate]


class SceneUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    actions: Optional[List[SceneActionCreate]] = None


class SceneActionResponse(BaseModel):
    id: int
    device_id: int
    device_name: str          # Populat din join, nu din ORM direct
    action: str
    value: Optional[str] = None
    order: int
    delay_seconds: int


class SceneResponse(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None
    is_active: bool
    actions: List[SceneActionResponse]
    created_at: datetime


# ---------------------------------------------------------------------------
# Command schemas
# ---------------------------------------------------------------------------


class CommandSend(BaseModel):
    device_id: int
    action: str
    value: Optional[str] = None


class CommandResponse(BaseModel):
    id: int
    device_id: int
    action: str
    value: Optional[str] = None
    source: str
    timestamp: datetime
    device_name: str


# ---------------------------------------------------------------------------
# Routine schemas
# ---------------------------------------------------------------------------


class RoutineCreate(BaseModel):
    name: str
    device_id: int
    action: str
    value: Optional[str] = None
    trigger_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    days_of_week: str

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: str) -> str:
        """Validează că zilele sunt cifre între 1 și 7, separate prin virgulă."""
        days = v.split(",")
        for day in days:
            if not day.strip().isdigit() or int(day.strip()) not in range(1, 8):
                raise ValueError("Zilele trebuie să fie numere între 1 și 7, separate prin virgulă")
        return v


class RoutineToggle(BaseModel):
    is_active: bool


class RoutineResponse(BaseModel):
    id: int
    user_id: int
    name: str
    device_id: int
    action: str
    value: Optional[str] = None
    trigger_time: str
    days_of_week: str
    is_active: bool
    is_ml_suggested: bool
    confidence: Optional[float] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Wake-on-LAN schemas
# ---------------------------------------------------------------------------


class WolRequest(BaseModel):
    device_id: int


# ---------------------------------------------------------------------------
# Notification schemas
# ---------------------------------------------------------------------------


class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# ActivityLog schemas
# ---------------------------------------------------------------------------


class ActivityLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# UserPreferences schemas
# ---------------------------------------------------------------------------


class UserPreferencesUpdate(BaseModel):
    timezone: Optional[str] = None
    language: Optional[str] = None
    theme: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    auto_detect_routines: Optional[bool] = None


class UserPreferencesResponse(BaseModel):
    id: int
    user_id: int
    timezone: str
    language: str
    theme: str
    notifications_enabled: bool
    auto_detect_routines: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    total_devices: int
    total_commands_today: int
    total_routines_active: int
    total_scenes: int
    most_used_device: Optional[str] = None
    peak_hour: Optional[int] = None
    # Comenzi per zi — ultimele 7 zile: [{"date": "2026-03-01", "count": 42}]
    commands_by_day: List[Dict[str, Any]]
    # Top 5 dispozitive: [{"device_name": "Bec Living", "count": 120}]
    commands_by_device: List[Dict[str, Any]]
    # Distribuție tipuri: [{"type": "ir_rgb", "count": 3}]
    device_type_distribution: List[Dict[str, Any]]
