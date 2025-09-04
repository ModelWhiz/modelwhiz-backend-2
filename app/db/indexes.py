"""
Database index optimization for ModelWhiz.
Defines indexes and utilities for query performance optimization.
"""

from sqlalchemy import text
from typing import Dict, List, Optional
import asyncio
from datetime import datetime

from .async_database import get_async_db
from app.utils.logger import log_error, get_logger
from app.utils.error_monitor import track_error, ErrorTypes
import uuid

class DatabaseIndexManager:
    """Manages database indexes and query optimization"""
    
    def __init__(self):
        self.index_definitions = {
            # ML Models table indexes (table name: ml_models)
            "idx_ml_models_user_id": "CREATE INDEX IF NOT EXISTS idx_ml_models_user_id ON ml_models(user_id)",
            "idx_ml_models_upload_time": "CREATE INDEX IF NOT EXISTS idx_ml_models_upload_time ON ml_models(upload_time)",
            "idx_ml_models_user_upload": "CREATE INDEX IF NOT EXISTS idx_ml_models_user_upload ON ml_models(user_id, upload_time)",
            "idx_ml_models_task_type": "CREATE INDEX IF NOT EXISTS idx_ml_models_task_type ON ml_models(task_type)",
            
            # Evaluation jobs table indexes (table name: evaluation_jobs)
            "idx_evaluation_jobs_user_id": "CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_user_id ON evaluation_jobs(user_id)",
            "idx_evaluation_jobs_created_at": "CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_created_at ON evaluation_jobs(created_at)",
            "idx_evaluation_jobs_status": "CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_status ON evaluation_jobs(status)",
            "idx_evaluation_jobs_model_id": "CREATE INDEX IF NOT EXISTS idx_evaluation_jobs_model_id ON evaluation_jobs(model_id)",
            
            # Metrics table indexes (table name: metrics)
            "idx_metrics_model_id": "CREATE INDEX IF NOT EXISTS idx_metrics_model_id ON metrics(model_id)",
            "idx_metrics_timestamp": "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)",
        }
    
    async def create_all_indexes(self):
        """Create all defined indexes"""
        success_count = 0
        total_count = len(self.index_definitions)
        
        db_gen = get_async_db()
        db = await db_gen.__anext__()
        
        try:
            for index_name, create_sql in self.index_definitions.items():
                try:
                    await db.execute(text(create_sql))
                    await db.commit()
                    print(f"Created index: {index_name}")
                    success_count += 1
                except Exception as e:
                    request_id = str(uuid.uuid4())
                    log_error(request_id, "index_creation_error", f"Failed to create index {index_name}: {e}")
                    await track_error(ErrorTypes.DATABASE, f"Index creation failed: {index_name} - {e}")
                    await db.rollback()
        
        finally:
            await db.close()
        
        print(f"Index creation completed: {success_count}/{total_count} indexes created")
        return success_count, total_count
    
    async def analyze_query_performance(self, query: str, params: Optional[Dict] = None) -> Dict:
        """
        Analyze query performance using EXPLAIN
        """
        try:
            db_gen = get_async_db()
            db = await db_gen.__anext__()
            
            try:
                explain_query = f"EXPLAIN {query}"
                result = await db.execute(text(explain_query), params or {})
                plan = result.fetchall()
                
                # Convert Row objects to strings for analysis
                plan_texts = [str(row[0]) if len(row) == 1 else str(row) for row in plan]
                
                analysis = {
                    "query": query,
                    "plan": plan_texts,
                    "uses_indexes": any("Index" in text or "index" in text for text in plan_texts),
                    "scan_type": self._get_scan_type(plan_texts),
                    "estimated_cost": self._estimate_cost(plan_texts)
                }
                
                return analysis
                
            finally:
                await db.close()
                
        except Exception as e:
            request_id = str(uuid.uuid4())
            log_error(request_id, "query_analysis_error", f"Query analysis failed: {e}")
            await track_error(ErrorTypes.DATABASE, f"Query analysis failed: {e}")
            return {"error": str(e)}
    
    def _get_scan_type(self, plan_texts: List[str]) -> str:
        """Determine the scan type from query plan"""
        for detail in plan_texts:
            if "SCAN TABLE" in detail:
                return "TABLE SCAN"
            elif "SEARCH TABLE" in detail and "USING INDEX" in detail:
                return "INDEX SEARCH"
            elif "SEARCH TABLE" in detail:
                return "TABLE SEARCH"
        return "UNKNOWN"
    
    def _estimate_cost(self, plan_texts: List[str]) -> int:
        """Estimate query cost based on plan"""
        cost = 0
        for detail in plan_texts:
            if "SCAN TABLE" in detail:
                cost += 100  # Table scans are expensive
            elif "SEARCH TABLE" in detail and "USING INDEX" in detail:
                cost += 10   # Index searches are efficient
            elif "SEARCH TABLE" in detail:
                return "TABLE SEARCH"
        return "UNKNOWN"
    
    async def get_index_usage_stats(self) -> Dict:
        """Get statistics on index usage"""
        try:
            db_gen = get_async_db()
            db = await db_gen.__anext__()
            
            try:
                # PostgreSQL specific query for index usage stats
                stats_query = """
                SELECT 
                    schemaname as schema_name,
                    tablename as table_name,
                    indexname as index_name,
                    indexdef as definition
                FROM pg_indexes 
                WHERE schemaname = 'public'
                AND tablename IN ('ml_models', 'evaluation_jobs', 'metrics')
                ORDER BY tablename, indexname
                """
                
                result = await db.execute(text(stats_query))
                indexes = [dict(row) for row in result.fetchall()]
                
                return {
                    "total_indexes": len(indexes),
                    "indexes_by_table": self._group_indexes_by_table(indexes),
                    "index_details": indexes
                }
                
            finally:
                await db.close()
                
        except Exception as e:
            request_id = str(uuid.uuid4())
            log_error(request_id, "index_stats_error", f"Failed to get index stats: {e}")
            await track_error(ErrorTypes.DATABASE, f"Index stats failed: {e}")
            return {"error": str(e)}
    
    def _group_indexes_by_table(self, indexes: List[Dict]) -> Dict:
        """Group indexes by table name"""
        grouped = {}
        for index in indexes:
            table_name = index['table_name']
            if table_name not in grouped:
                grouped[table_name] = []
            grouped[table_name].append({
                "name": index['index_name'],
                "definition": index['definition']
            })
        return grouped
    
    async def optimize_queries(self, queries: List[str]) -> List[Dict]:
        """
        Analyze and suggest optimizations for multiple queries
        """
        results = []
        for query in queries:
            analysis = await self.analyze_query_performance(query)
            suggestions = self._generate_optimization_suggestions(analysis)
            
            results.append({
                "query": query,
                "analysis": analysis,
                "suggestions": suggestions,
                "optimized": bool(suggestions)
            })
        
        return results
    
    def _generate_optimization_suggestions(self, analysis: Dict) -> List[str]:
        """Generate optimization suggestions based on query analysis"""
        suggestions = []
        
        if not analysis.get('uses_indexes', False):
            suggestions.append("Consider adding appropriate indexes for WHERE clauses")
        
        if analysis.get('scan_type') == 'TABLE SCAN':
            suggestions.append("Table scan detected - add indexes to avoid full table scans")
        
        if analysis.get('estimated_cost', 0) > 50:
            suggestions.append("High estimated cost - consider query optimization")
        
        return suggestions

# Global index manager instance
index_manager = DatabaseIndexManager()

# Utility functions
async def create_indexes():
    """Create all database indexes"""
    return await index_manager.create_all_indexes()

async def analyze_query(query: str, params: Optional[Dict] = None):
    """Analyze a single query's performance"""
    return await index_manager.analyze_query_performance(query, params)

async def get_index_stats():
    """Get index usage statistics"""
    return await index_manager.get_index_usage_stats()

async def optimize_query_list(queries: List[str]):
    """Optimize multiple queries"""
    return await index_manager.optimize_queries(queries)
