from celery import Celery
import os
import logging

logger = logging.getLogger(__name__)

# Check if Redis is available, fallback to in-memory broker if not
def get_redis_url():
    """Get Redis URL from environment variable"""
    redis_url = os.getenv("REDIS_BROKER_URL")
    if redis_url:
        logger.info(f"Using Redis broker URL from environment: {redis_url}")
        return redis_url
    else:
        logger.warning("REDIS_BROKER_URL not set, using in-memory broker")
        return "memory://"

# Celery configuration with Redis fallback
REDIS_BROKER_URL = get_redis_url()
REDIS_RESULT_BACKEND = os.getenv("REDIS_RESULT_BACKEND") if "redis://" in REDIS_BROKER_URL else "rpc://"

# Log the Redis URLs for debugging
logger.info(f"Celery Redis Broker URL: {REDIS_BROKER_URL}")
logger.info(f"Celery Redis Result Backend: {REDIS_RESULT_BACKEND}")

celery_app = Celery(
    "modelwhiz_workers",
    broker=REDIS_BROKER_URL,
    backend=REDIS_RESULT_BACKEND,
    include=["app.workers.tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task routing and priorities
    task_routes={
        "app.workers.tasks.evaluate_model_async": {"queue": "ml_tasks", "priority": 5},
        "app.workers.tasks.cleanup_old_files": {"queue": "maintenance", "priority": 8},
        "app.workers.tasks.generate_model_insights": {"queue": "ml_tasks", "priority": 6},
        "app.workers.tasks.update_model_statistics": {"queue": "maintenance", "priority": 7},
        "app.workers.tasks.health_check_system": {"queue": "maintenance", "priority": 9},
        "app.workers.tasks.process_evaluation_task": {"queue": "ml_tasks", "priority": 5},
        "app.workers.tasks.evaluate_model_with_perf_tracking": {"queue": "ml_tasks", "priority": 5},
        "app.workers.tasks.preprocess_data_with_perf_tracking": {"queue": "ml_tasks", "priority": 6},
    },
    
    # Worker concurrency settings
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", 4)),
    worker_prefetch_multiplier=int(os.getenv("CELERY_WORKER_PREFETCH_MULTIPLIER", 1)),
    
    # Task acknowledgment settings
    task_acks_late=os.getenv("CELERY_TASK_ACKS_LATE", "true").lower() == "true",
    
    # Rate limiting
    task_annotations={
        "*": {"rate_limit": "10/s"}
    },

    # Task timeout settings to prevent hanging tasks
    task_time_limit=1800,  # Hard time limit: 30 minutes
    task_soft_time_limit=1500,  # Soft time limit: 25 minutes

    # Monitoring and events
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Connection retry settings - Enhanced for better reliability
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=20,  # Increased retries
    broker_connection_retry_delay=1.0,  # Start with 1 second delay
    
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'cleanup-old-files': {
            'task': 'app.workers.tasks.cleanup_old_files',
            'schedule': 3600.0,  # Every hour
        },
        'update-model-statistics': {
            'task': 'app.workers.tasks.update_model_statistics',
            'schedule': 1800.0,  # Every 30 minutes
        },
        'health-check-system': {
            'task': 'app.workers.tasks.health_check_system',
            'schedule': 300.0,  # Every 5 minutes
        },
    },
    
    # Worker settings
    worker_disable_rate_limits=os.getenv("CELERY_WORKER_DISABLE_RATE_LIMITS", "false").lower() == "true",
    
    # Task routing
    task_default_queue='default',
    task_default_exchange='default',
    task_default_routing_key='default',
    
    # Enhanced error handling
    task_reject_on_worker_lost=True,
    task_always_eager=False,  # Set to True for testing without Redis
    
    # Redis connection pool settings (only if using Redis)
    broker_transport_options={
        'visibility_timeout': 3600,
        'fanout_prefix': True,
        'fanout_patterns': True,
    } if "redis://" in REDIS_BROKER_URL else {},
    
    # Result backend transport options
    result_backend_transport_options={
        'retry_policy': {
            'timeout': 5.0
        },
        'visibility_timeout': 3600,
    } if "redis://" in REDIS_BROKER_URL else {}
)

# Auto-discover tasks from tasks.py
celery_app.autodiscover_tasks(["app.workers.tasks"])

# Health check task
@celery_app.task
def health_check():
    """Simple health check task for Celery"""
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}

# Test task
@celery_app.task
def test_task():
    """Test task for debugging"""
    return {"message": "Test task executed successfully"}
