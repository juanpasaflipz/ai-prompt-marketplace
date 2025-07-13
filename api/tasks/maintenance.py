"""
System maintenance background tasks.

Handles cleanup, optimization, and regular maintenance operations.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import text, and_
import os
import shutil

from api.database import get_db, engine
from api.models.analytics import AnalyticsEvent
from api.models.session import Session
from api.models.cache import CacheEntry
from api.models.user import User
from api.models.prompt import Prompt
from api.services.cache_service import get_cache_service
from api.config import settings

logger = get_task_logger(__name__)
cache = get_cache_service(
    host=settings.redis_host,
    port=settings.redis_port,
    password=settings.redis_password,
    db=settings.redis_db
)


@shared_task(bind=True)
def clean_expired_sessions(self, days_to_keep: int = 30):
    """
    Clean up expired user sessions from the database.
    
    Removes sessions older than the specified number of days to prevent
    the sessions table from growing too large.
    """
    try:
        logger.info(f"Starting session cleanup (keeping last {days_to_keep} days)")
        
        db = next(get_db())
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Delete expired sessions
        deleted_count = db.query(Session).filter(
            Session.last_activity < cutoff_date
        ).delete()
        
        # Also delete sessions that have been explicitly marked as expired
        expired_count = db.query(Session).filter(
            Session.is_expired == True
        ).delete()
        
        db.commit()
        db.close()
        
        total_deleted = deleted_count + expired_count
        logger.info(f"Cleaned up {total_deleted} expired sessions ({deleted_count} old, {expired_count} marked expired)")
        
        # Clear session-related caches
        cache.delete_pattern("session:*")
        
        return {
            "status": "success",
            "sessions_deleted": total_deleted,
            "cutoff_date": cutoff_date.isoformat(),
            "cleaned_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning expired sessions: {e}")
        raise


@shared_task(bind=True)
def clean_old_analytics(self, days_to_keep: int = 90):
    """
    Clean up old analytics data to manage database size.
    
    Archives or removes analytics events older than the retention period.
    """
    try:
        logger.info(f"Starting analytics cleanup (keeping last {days_to_keep} days)")
        
        db = next(get_db())
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # First, aggregate old data into summary statistics
        summary_data = db.execute(
            text("""
                SELECT 
                    DATE(created_at) as event_date,
                    event_type,
                    COUNT(*) as event_count,
                    COUNT(DISTINCT user_id) as unique_users
                FROM analytics_events
                WHERE created_at < :cutoff_date
                GROUP BY DATE(created_at), event_type
            """),
            {"cutoff_date": cutoff_date}
        ).fetchall()
        
        # Store summary in cache or archive table
        if summary_data:
            archive_key = f"analytics:archive:{cutoff_date.date()}"
            archive_data = [
                {
                    "date": row.event_date.isoformat(),
                    "event_type": row.event_type,
                    "count": row.event_count,
                    "unique_users": row.unique_users
                }
                for row in summary_data
            ]
            cache.set(archive_key, archive_data, ttl=86400 * 365)  # Keep for 1 year
            
            logger.info(f"Archived {len(summary_data)} daily summaries")
        
        # Delete old events
        deleted_count = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.created_at < cutoff_date
        ).delete()
        
        db.commit()
        
        # Vacuum analyze the table to reclaim space (PostgreSQL specific)
        if settings.database_url.startswith("postgresql"):
            db.execute(text("VACUUM ANALYZE analytics_events"))
            db.commit()
        
        db.close()
        
        logger.info(f"Deleted {deleted_count} old analytics events")
        
        return {
            "status": "success",
            "events_deleted": deleted_count,
            "summaries_archived": len(summary_data) if summary_data else 0,
            "cutoff_date": cutoff_date.isoformat(),
            "cleaned_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cleaning old analytics: {e}")
        raise


@shared_task(bind=True)
def optimize_database(self):
    """
    Perform database optimization tasks.
    
    Runs maintenance operations like reindexing, analyzing tables,
    and updating statistics for better query performance.
    """
    try:
        logger.info("Starting database optimization")
        
        db = next(get_db())
        optimization_results = {}
        
        # Get list of tables
        if settings.database_url.startswith("postgresql"):
            # PostgreSQL optimization
            tables = db.execute(
                text("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
            ).fetchall()
            
            for table in tables:
                table_name = table.tablename
                
                try:
                    # Analyze table to update statistics
                    db.execute(text(f"ANALYZE {table_name}"))
                    
                    # Get table size
                    size_result = db.execute(
                        text(f"""
                            SELECT 
                                pg_size_pretty(pg_total_relation_size('{table_name}')) as total_size,
                                pg_size_pretty(pg_relation_size('{table_name}')) as table_size
                        """)
                    ).fetchone()
                    
                    # Get row count
                    row_count = db.execute(
                        text(f"SELECT COUNT(*) FROM {table_name}")
                    ).scalar()
                    
                    optimization_results[table_name] = {
                        "status": "optimized",
                        "row_count": row_count,
                        "total_size": size_result.total_size if size_result else "unknown",
                        "table_size": size_result.table_size if size_result else "unknown"
                    }
                    
                except Exception as e:
                    optimization_results[table_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    logger.error(f"Error optimizing table {table_name}: {e}")
            
            # Reindex tables if needed
            db.execute(text("REINDEX DATABASE CONCURRENTLY current_database()"))
            
        elif settings.database_url.startswith("mysql"):
            # MySQL optimization
            tables = db.execute(
                text("SHOW TABLES")
            ).fetchall()
            
            for table in tables:
                table_name = table[0]
                
                try:
                    # Optimize table
                    db.execute(text(f"OPTIMIZE TABLE {table_name}"))
                    
                    # Get table status
                    status = db.execute(
                        text(f"SHOW TABLE STATUS LIKE '{table_name}'")
                    ).fetchone()
                    
                    optimization_results[table_name] = {
                        "status": "optimized",
                        "row_count": status.Rows if status else 0,
                        "data_length": status.Data_length if status else 0,
                        "index_length": status.Index_length if status else 0
                    }
                    
                except Exception as e:
                    optimization_results[table_name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    logger.error(f"Error optimizing table {table_name}: {e}")
        
        db.commit()
        db.close()
        
        # Clean up cache
        cache_stats = self._clean_cache()
        
        # Clean up temporary files
        temp_stats = self._clean_temp_files()
        
        logger.info("Database optimization completed")
        
        return {
            "status": "success",
            "tables_optimized": len([t for t in optimization_results.values() if t["status"] == "optimized"]),
            "optimization_results": optimization_results,
            "cache_cleaned": cache_stats,
            "temp_files_cleaned": temp_stats,
            "optimized_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error optimizing database: {e}")
        raise

def _clean_cache(self) -> Dict[str, Any]:
    """Clean up expired cache entries."""
    try:
        # Clear expired Redis keys
        expired_keys = cache.delete_expired()
        
        # Clear specific cache patterns that might be stale
        patterns_to_clean = [
            "prompt:preview:*",  # Old prompt previews
            "user:session:*",    # Old user sessions
            "analytics:temp:*",  # Temporary analytics data
            "rate_limit:*"       # Old rate limit entries
        ]
        
        cleaned_patterns = {}
        for pattern in patterns_to_clean:
            count = cache.delete_pattern(pattern)
            cleaned_patterns[pattern] = count
        
        return {
            "expired_keys_removed": expired_keys,
            "patterns_cleaned": cleaned_patterns,
            "total_removed": expired_keys + sum(cleaned_patterns.values())
        }
        
    except Exception as e:
        logger.error(f"Error cleaning cache: {e}")
        return {"error": str(e)}

def _clean_temp_files(self) -> Dict[str, Any]:
    """Clean up temporary files and directories."""
    try:
        temp_dirs = [
            "/tmp/ai-marketplace-uploads",
            "/tmp/ai-marketplace-exports",
            os.path.join(settings.base_dir, "temp")
        ]
        
        files_removed = 0
        space_freed = 0
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                # Remove files older than 24 hours
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            file_stat = os.stat(file_path)
                            file_modified = datetime.fromtimestamp(file_stat.st_mtime)
                            
                            if file_modified < cutoff_time:
                                space_freed += file_stat.st_size
                                os.remove(file_path)
                                files_removed += 1
                                
                        except Exception as e:
                            logger.warning(f"Error removing file {file_path}: {e}")
        
        return {
            "files_removed": files_removed,
            "space_freed_mb": round(space_freed / (1024 * 1024), 2)
        }
        
    except Exception as e:
        logger.error(f"Error cleaning temp files: {e}")
        return {"error": str(e)}


@shared_task(bind=True)
def check_system_health(self):
    """
    Perform system health checks.
    
    Monitors database connections, cache availability, and other system resources.
    """
    try:
        logger.info("Running system health check")
        
        health_status = {
            "database": {"status": "unknown"},
            "cache": {"status": "unknown"},
            "storage": {"status": "unknown"},
            "services": {},
            "checked_at": datetime.utcnow().isoformat()
        }
        
        # Check database
        try:
            db = next(get_db())
            db.execute(text("SELECT 1"))
            db.close()
            health_status["database"]["status"] = "healthy"
            
            # Get connection pool stats
            pool_status = engine.pool.status()
            health_status["database"]["pool_status"] = pool_status
            
        except Exception as e:
            health_status["database"]["status"] = "unhealthy"
            health_status["database"]["error"] = str(e)
            logger.error(f"Database health check failed: {e}")
        
        # Check cache
        try:
            test_key = "health:check:test"
            cache.set(test_key, "test", ttl=10)
            value = cache.get(test_key)
            cache.delete(test_key)
            
            if value == "test":
                health_status["cache"]["status"] = "healthy"
                
                # Get cache stats
                info = cache.client.info()
                health_status["cache"]["stats"] = {
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0)
                }
            else:
                health_status["cache"]["status"] = "unhealthy"
                
        except Exception as e:
            health_status["cache"]["status"] = "unhealthy"
            health_status["cache"]["error"] = str(e)
            logger.error(f"Cache health check failed: {e}")
        
        # Check storage
        try:
            # Get disk usage
            disk_usage = shutil.disk_usage("/")
            health_status["storage"] = {
                "status": "healthy" if disk_usage.free > 1024 * 1024 * 1024 else "warning",  # 1GB threshold
                "total_gb": round(disk_usage.total / (1024 * 1024 * 1024), 2),
                "used_gb": round(disk_usage.used / (1024 * 1024 * 1024), 2),
                "free_gb": round(disk_usage.free / (1024 * 1024 * 1024), 2),
                "percent_used": round((disk_usage.used / disk_usage.total) * 100, 2)
            }
            
        except Exception as e:
            health_status["storage"]["status"] = "unknown"
            health_status["storage"]["error"] = str(e)
        
        # Check external services (placeholder)
        services_to_check = ["stripe", "openai", "email"]
        for service in services_to_check:
            # In a real implementation, you would check actual service connectivity
            health_status["services"][service] = {
                "status": "assumed_healthy",
                "last_check": datetime.utcnow().isoformat()
            }
        
        # Store health status in cache for monitoring
        cache.set("system:health:latest", health_status, ttl=300)  # 5 minutes
        
        # Determine overall status
        critical_services = ["database", "cache"]
        overall_healthy = all(
            health_status.get(service, {}).get("status") == "healthy"
            for service in critical_services
        )
        
        health_status["overall_status"] = "healthy" if overall_healthy else "unhealthy"
        
        logger.info(f"System health check completed: {health_status['overall_status']}")
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error during system health check: {e}")
        raise