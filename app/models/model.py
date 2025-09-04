# modelwhiz-backend/app/models/model.py

from sqlalchemy import Column, Integer, String, DateTime, Float, JSON
from datetime import datetime
from ..db.database import Base
from sqlalchemy.orm import relationship

class MLModel(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    name = Column(String, index=True)
    version = Column(String, default="v1")
    filename = Column(String)
    upload_time = Column(DateTime, default=datetime.utcnow)
    latest_metrics = Column(JSON, nullable=True)
    task_type = Column(String, nullable=True)  # Will store 'classification' or 'regression'
    metrics = relationship("Metric", back_populates="model", cascade="all, delete-orphan")
    evaluation_jobs = relationship("EvaluationJob", back_populates="model", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert SQLAlchemy model to dictionary for serialization"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "version": self.version,
            "filename": self.filename,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "latest_metrics": self.latest_metrics,
            "task_type": self.task_type
        }