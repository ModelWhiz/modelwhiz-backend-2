# modelwhiz-backend/app/models/evaluation_job.py

from sqlalchemy import Column, Integer, String, JSON, DateTime, Enum as SQLAlchemyEnum, ForeignKey
from sqlalchemy.sql import func
from ..db.database import Base
import enum
from sqlalchemy.orm import relationship

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class EvaluationJob(Base):
    __tablename__ = "evaluation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    model_name = Column(String, nullable=False)
    model_id = Column(Integer, ForeignKey("ml_models.id"), nullable=False)

    status = Column(SQLAlchemyEnum(JobStatus), default=JobStatus.PENDING)
    task_id = Column(String, nullable=True, index=True)  # Celery task ID for tracking
    results = Column(JSON, nullable=True)
    artifacts = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    model = relationship("MLModel", back_populates="evaluation_jobs")
    
    def to_dict(self):
        """Convert SQLAlchemy model to dictionary for serialization"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "model_name": self.model_name,
            "model_id": self.model_id,
            "status": self.status.value if self.status else None,
            "task_id": self.task_id,
            "results": self.results,
            "artifacts": self.artifacts,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
    
    def update_status(self, new_status: JobStatus, task_id: str = None, error_message: str = None):
        """Update job status and related fields"""
        self.status = new_status
        if task_id:
            self.task_id = task_id
        if error_message:
            self.error_message = error_message
        if new_status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            from datetime import datetime
            self.completed_at = datetime.utcnow()