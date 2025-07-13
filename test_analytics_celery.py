#!/usr/bin/env python3
"""
Test script to verify the Celery-based analytics service.

Run this after starting Redis and Celery workers:
    celery -A api.celery_app worker --loglevel=info -Q analytics
"""

import sys
import time
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/Users/juan/Desktop/VSCode/quick-ship-high-traction/generative-ai-prompt-marketplace/ai-prompt-marketplace')

from api.services.analytics_service import analytics_service, EventType


def test_analytics_with_celery():
    """Test the analytics service with Celery background processing."""
    
    print("Testing Analytics Service with Celery...")
    print("-" * 50)
    
    # Check initial queue size
    initial_size = analytics_service.get_queue_size()
    print(f"Initial queue size: {initial_size}")
    
    # Track some test events
    test_events = [
        {
            "user_id": "test-user-1",
            "event_type": EventType.PROMPT_VIEWED,
            "entity_type": "prompt",
            "entity_id": "test-prompt-1",
            "metadata": {"source": "homepage"},
        },
        {
            "user_id": "test-user-2", 
            "event_type": EventType.PROMPT_CLICKED,
            "entity_type": "prompt",
            "entity_id": "test-prompt-2",
            "metadata": {"source": "search"},
        },
        {
            "user_id": "test-user-1",
            "event_type": EventType.PROMPT_PURCHASED,
            "entity_type": "prompt", 
            "entity_id": "test-prompt-1",
            "metadata": {"price": 9.99},
        },
    ]
    
    # Track events
    for i, event in enumerate(test_events):
        analytics_service.track_event(**event)
        print(f"Tracked event {i+1}: {event['event_type']}")
    
    # Check queue size after tracking
    queue_size = analytics_service.get_queue_size()
    print(f"\nQueue size after tracking: {queue_size}")
    
    # Manually trigger flush
    print("\nManually triggering flush...")
    flushed = analytics_service.flush_events_now()
    if flushed:
        print("Flush triggered successfully!")
    else:
        print("No events to flush or flush failed")
    
    # Give Celery time to process
    print("\nWaiting for Celery to process...")
    time.sleep(2)
    
    # Check final queue size
    final_size = analytics_service.get_queue_size()
    print(f"Final queue size: {final_size}")
    
    print("\n" + "-" * 50)
    print("Test completed! Check Celery worker logs for processing details.")
    print("\nTo see the flushed events in the database, run:")
    print("psql -d your_database -c 'SELECT * FROM analytics_events ORDER BY created_at DESC LIMIT 10;'")


if __name__ == "__main__":
    test_analytics_with_celery()