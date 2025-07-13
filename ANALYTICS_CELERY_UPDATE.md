# Analytics Service - Celery Integration Update

## Overview

The analytics service has been updated to use Celery for background processing instead of in-memory queuing with asyncio. This provides better scalability, reliability, and integration with the existing Celery infrastructure.

## Changes Made

### 1. Removed In-Memory Components
- Removed `collections.deque` for event storage
- Removed `asyncio` background flush task
- Removed async event loop management

### 2. Added Redis-Based Caching
- Events are now stored in Redis using the cache service
- Key: `analytics:events:batch`
- Serialization: Pickle format for complex objects

### 3. Integrated Celery Tasks
- Event flushing is now handled by the `flush_analytics_events` Celery task
- Task runs on the 'analytics' queue
- Automatic retry on failure (up to 3 attempts)

### 4. Updated Event Structure
The analytics task now properly handles all event fields:
- `user_id`
- `session_id`
- `event_type`
- `entity_type`
- `entity_id`
- `event_metadata` (automatically parsed from JSON string)
- `ip_address`
- `user_agent`
- `referrer`
- `created_at`

## New Methods

### `flush_events_now()`
Manually trigger event flush - useful for graceful shutdown or testing.

```python
analytics_service.flush_events_now()
```

### `get_queue_size()`
Get the current number of events waiting to be flushed.

```python
queue_size = analytics_service.get_queue_size()
```

## Configuration

The service uses these settings from `api.config`:
- `redis_host`: Redis server host
- `redis_port`: Redis server port
- `redis_password`: Redis password (if required)
- `redis_db`: Redis database number
- `analytics_batch_size`: Number of events to batch (default: 100)
- `analytics_flush_interval`: Flush interval in seconds (default: 60)

## Celery Worker Setup

Start a Celery worker for analytics processing:

```bash
# Start worker for analytics queue
celery -A api.celery_app worker --loglevel=info -Q analytics

# Or start all queues
celery -A api.celery_app worker --loglevel=info
```

## Celery Beat Setup

The analytics flush task is configured to run every 60 seconds via Celery Beat:

```bash
# Start Celery Beat scheduler
celery -A api.celery_app beat --loglevel=info
```

## Testing

Use the provided test script to verify the integration:

```bash
python test_analytics_celery.py
```

## Benefits of Celery Integration

1. **Reliability**: Events are persisted in Redis, preventing data loss on service restart
2. **Scalability**: Can scale by adding more Celery workers
3. **Monitoring**: Celery provides built-in monitoring and management tools
4. **Retry Logic**: Automatic retry on failure with exponential backoff
5. **Distributed Processing**: Events can be processed by workers on different machines
6. **Integration**: Works seamlessly with existing Celery infrastructure

## Migration Notes

- The service maintains the same public API
- Existing code using `track_event()` continues to work without changes
- Events are now more reliably persisted even if the main application crashes
- The periodic flush is handled by Celery Beat instead of asyncio

## Performance Considerations

- Redis operations are atomic and thread-safe
- The service uses a lock only when updating the batch to ensure consistency
- Batch size can be tuned based on your workload
- Consider Redis memory usage for large batch sizes

## Monitoring

Monitor the analytics pipeline using:
- Celery Flower for task monitoring
- Redis CLI to check queue sizes
- Application logs for tracking and flush events
- Database queries to verify event persistence