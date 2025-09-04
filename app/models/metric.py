# modelwhiz-backend/app/models/metric.py

from sqlalchemy import Column, Integer, ForeignKey, DateTime, JSON # <-- Import JSON
from sqlalchemy.sql import func
from ..db.database import Base
from sqlalchemy.orm import relationship

class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("ml_models.id"))
    values = Column(JSON, nullable=False)

    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    model = relationship("MLModel", back_populates="metrics")