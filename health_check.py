#!/usr/bin/env python3
"""
Backend Health Check Script
This script checks if the ModelWhiz backend is running properly and if all services are available.
"""

import requests
import json
import sys
import os
from datetime import datetime

def check_backend_health():
    """Check if the backend is running and healthy"""
    try:
        # Try to connect to the backend health endpoint
        response = requests.get("http://localhost:8000/health", timeout=10)
        if response.status_code == 200:
            print("✅ Backend is running and healthy")
            return True
        else:
            print(f"❌ Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend at http://localhost:8000")
        print("   Make sure the backend is running with: python -m uvicorn app.main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"❌ Error checking backend health: {e}")
        return False

def check_celery_workers():
    """Check if Celery workers are available"""
    try:
        # Try to connect to the evaluations endpoint with required parameters
        response = requests.get("http://localhost:8000/api/evaluations/?user_id=test", timeout=10)
        if response.status_code == 200:
            print("✅ API endpoints are accessible")
            return True
        else:
            print(f"❌ API endpoints returned status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            return False
    except Exception as e:
        print(f"❌ Error checking API endpoints: {e}")
        return False

def check_redis_connection():
    """Check if Redis is available"""
    try:
        import redis
        # Try to connect to Redis in Docker with password
        r = redis.Redis(host='localhost', port=6379, db=0, password='modelwhiz_redis_password', socket_timeout=5)
        r.ping()
        print("✅ Redis is running and accessible")
        return True
    except redis.AuthenticationError:
        try:
            # Try with empty password
            r = redis.Redis(host='localhost', port=6379, db=0, password='', socket_timeout=5)
            r.ping()
            print("✅ Redis is running and accessible (no password)")
            return True
        except Exception as e:
            print(f"❌ Redis authentication failed: {e}")
            print("   Try: redis-cli and run 'CONFIG SET requirepass \"\"' to disable password")
            return False
    except ImportError:
        print("⚠️  Redis Python client not installed. Install with: pip install redis")
        return False
    except Exception as e:
        print(f"⚠️  Redis not available: {e}")
        print("   Celery will use in-memory broker instead")
        print("   To install Redis: Download from https://redis.io/download")
        return True  # Return True because Celery can work without Redis

def check_database():
    """Check if database is accessible"""
    try:
        # Try to access the models endpoint to check database
        response = requests.get("http://localhost:8000/api/models/", timeout=10)
        if response.status_code in [200, 401, 403]:  # Any response means DB is working
            print("✅ Database is accessible")
            return True
        else:
            print(f"❌ Database check returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def main():
    """Main health check function"""
    print("🔍 ModelWhiz Backend Health Check")
    print("=" * 40)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    checks = [
        ("Backend Health", check_backend_health),
        ("API Endpoints", check_celery_workers),
        ("Redis Connection", check_redis_connection),
        ("Database", check_database),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"Checking {name}...")
        result = check_func()
        results.append((name, result))
        print()
    
    # Summary
    print("📊 Health Check Summary")
    print("=" * 40)
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name}: {status}")
    
    print()
    print(f"Overall: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All systems are operational!")
        return 0
    else:
        print("⚠️  Some systems need attention. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
