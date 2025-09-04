# Import all models to ensure proper relationship configuration
from .model import MLModel
from .metric import Metric
from .evaluation_job import EvaluationJob

# Export all models
__all__ = ["MLModel", "Metric", "EvaluationJob"]
