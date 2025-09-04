"""
Standardized cache key generation and TTL management
"""

# --- TTL Constants (in seconds) ---
MODEL_LIST_TTL = 120        # 2 minutes
MODEL_DETAIL_TTL = 300      # 5 minutes
EVALUATION_RESULT_TTL = 3600 # 1 hour
USER_PROFILE_TTL = 1800     # 30 minutes
STATS_TTL = 900             # 15 minutes

# --- Key Generation Functions ---

def model_list_key(user_id: str) -> str:
    """
    Generates cache key for user's model list
    Example: "models:list:user:12345"
    """
    return f"models:list:user:{user_id}"

def model_detail_key(model_id: int) -> str:
    """
    Generates cache key for model details
    Example: "models:detail:678"
    """
    return f"models:detail:{model_id}"

def evaluation_result_key(job_id: str) -> str:
    """
    Generates cache key for evaluation results
    Example: "evaluation:result:job_abc123"
    """
    return f"evaluation:result:{job_id}"

def user_models_key(user_id: int) -> str:
    """
    Generates cache key for user's models with metadata
    Example: "user:12345:models"
    """
    return f"user:{user_id}:models"

def model_stats_key(model_id: int) -> str:
    """
    Generates cache key for model statistics
    Example: "models:stats:678"
    """
    return f"models:stats:{model_id}"

# --- Key Pattern Functions for Invalidation ---

def model_list_pattern(user_id: int) -> str:
    """Pattern to match user's model list cache"""
    return f"models:list:user:{user_id}"

def model_detail_pattern(model_id: int) -> str:
    """Pattern to match model detail cache"""
    return f"models:detail:{model_id}"

def user_related_pattern(user_id: int) -> str:
    """Pattern to match all user-related cache entries"""
    return f"*user:{user_id}*"

def model_related_pattern(model_id: int) -> str:
    """Pattern to match all model-related cache entries"""
    return f"models:*:{model_id}"

def all_models_pattern() -> str:
    """Pattern to match all model cache entries"""
    return "models:*"

# --- Cache Key Generators for Decorators ---

def generate_model_list_key(user_id: str = None, cursor: str = None, limit: int = 20, db = None, **kwargs) -> str:
    """
    Extract user_id from function args and generate cache key
    Handles FastAPI function signature
    """
    # Use user_id from kwargs or default to anonymous
    user_id = user_id or kwargs.get('user_id', 'anonymous')
    
    return model_list_key(user_id)

def generate_model_detail_key(model_id: int, db = None, **kwargs) -> str:
    """
    Extract model_id from function args and generate cache key
    """
    return model_detail_key(model_id)

def generate_evaluation_key(*args, **kwargs) -> str:
    """
    Extract job_id from function args and generate cache key
    """
    job_id = None
    
    if 'job_id' in kwargs:
        job_id = kwargs['job_id']
    elif args and isinstance(args[0], str):
        job_id = args[0]
    
    if job_id is None:
        raise ValueError("Could not extract job_id for cache key generation")
    
    return evaluation_result_key(job_id)

# --- Invalidation Pattern Generators for Decorators ---

def generate_model_invalidation_patterns(*args, **kwargs) -> list[str]:
    """
    Generate patterns to invalidate when model data changes
    Returns list of patterns to clear related caches
    """
    patterns = []
    
    # Extract user_id and model_id if available
    user_id = kwargs.get('user_id')
    model_id = kwargs.get('model_id')
    
    # Handle different argument structures
    if not user_id and args:
        if hasattr(args[0], 'user_id'):
            user_id = args[0].user_id
        elif len(args) > 1:
            user_id = args[1] if isinstance(args[1], int) else None
    
    if not model_id and args:
        if isinstance(args[0], int):
            model_id = args[0]
    
    # Add patterns based on available IDs
    if user_id:
        patterns.append(model_list_pattern(user_id))
        patterns.append(user_related_pattern(user_id))
    
    if model_id:
        patterns.append(model_detail_pattern(model_id))
        patterns.append(model_related_pattern(model_id))
    
    return patterns

def generate_user_invalidation_patterns(*args, **kwargs) -> list[str]:
    """
    Generate patterns to invalidate user-related caches
    """
    user_id = kwargs.get('user_id')
    
    if not user_id and args:
        if hasattr(args[0], 'user_id'):
            user_id = args[0].user_id
        elif isinstance(args[0], int):
            user_id = args[0]
    
    if user_id:
        return [user_related_pattern(user_id)]
    
    return []