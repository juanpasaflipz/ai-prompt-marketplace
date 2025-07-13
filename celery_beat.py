#!/usr/bin/env python3
"""
Celery beat scheduler entry point.

Run with: celery -A celery_beat beat --loglevel=info
"""

import os
import sys

# Add the parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.celery_app import celery_app

if __name__ == '__main__':
    celery_app.start()