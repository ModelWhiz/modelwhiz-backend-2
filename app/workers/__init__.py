"""
ModelWhiz background task workers package.
Contains Celery configuration and task definitions for asynchronous processing.
"""

from .celery_app import celery_app

__all__ = ['celery_app']
