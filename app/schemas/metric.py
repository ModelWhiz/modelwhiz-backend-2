from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime


class MetricCreate(BaseModel):
    model_id: int
    accuracy: float
    f1_score: float
    auc: float

class MetricOut(BaseModel):
    model_id: int
    values: Dict[str, Any] # The flexible dictionary for metrics
    timestamp: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)