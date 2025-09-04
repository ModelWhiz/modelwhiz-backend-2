from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from .metric import MetricOut
from datetime import datetime

class ModelCreate(BaseModel):
    name: str
    filename: str
    user_id: str
    task_type: str

class ModelResponse(BaseModel):
    id: int
    name: str
    version: str
    filename: str
    upload_time: datetime
    user_id: str
    latest_metrics: Optional[Dict[str, Any]] = None
    task_type: Optional[str] = None
    metrics: Optional[List[MetricOut]] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        },
        exclude_none=True
    )

class ModelDashboardOut(BaseModel):
    id: int
    name: str
    version: str
    filename: str
    upload_time: datetime
    user_id: str
    latest_metrics: Optional[Dict[str, Any]] = {}
    task_type: Optional[str] = None
    # metrics: Optional[List[MetricOut]] = []

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        },
        exclude_none=True
    )

class ModelListResponse(BaseModel):
    id: int
    name: str
    version: str
    upload_time: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        }
    )

class ModelDetailResponse(BaseModel):
    id: int
    name: str
    version: str
    filename: str
    upload_time: datetime
    user_id: str
    latest_metrics: Optional[Dict[str, Any]] = {}
    task_type: Optional[str] = None
    metrics: Optional[List[MetricOut]] = []

    model_config = ConfigDict(from_attributes=True)

class ModelPaginatedResponse(BaseModel):
    items: List[ModelDashboardOut]
    total: int
    page: int
    pages: int
    has_next: bool
    next_cursor: Optional[str] = None
        
class ModelUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model_type: Optional[str] = None
    # Add other updateable fields
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
        },
        exclude_none=True
    )
