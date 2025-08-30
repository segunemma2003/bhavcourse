#!/usr/bin/env python3
"""
Simple script to check if Celery workers are running
"""

import os
import sys
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'courseapp.settings')
django.setup()

def check_celery_workers():
    """Check if Celery workers are running"""
    print("🔍 Checking Celery Workers...")
    
    try:
        from celery import current_app
        
        # Get Celery app
        app = current_app
        print(f"✅ Celery app loaded: {app}")
        
        # Check if workers are running
        inspect = app.control.inspect()
        
        # Check active workers
        active = inspect.active()
        if active:
            print("✅ Active workers found:")
            for worker, tasks in active.items():
                print(f"   {worker}: {len(tasks)} active tasks")
        else:
            print("ℹ️  No active tasks")
        
        # Check registered workers
        registered = inspect.registered()
        if registered:
            print("✅ Registered workers:")
            for worker, tasks in registered.items():
                print(f"   {worker}: {len(tasks)} registered tasks")
        else:
            print("❌ No registered workers found")
            return False
        
        # Check worker stats
        stats = inspect.stats()
        if stats:
            print("✅ Worker statistics:")
            for worker, info in stats.items():
                print(f"   {worker}:")
                print(f"     Pool: {info.get('pool', {}).get('implementation', 'Unknown')}")
                print(f"     Processed: {info.get('total', {}).get('processed', 0)}")
                print(f"     Load: {info.get('load', [0, 0, 0])}")
        else:
            print("❌ No worker statistics available")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking workers: {e}")
        return False

def check_redis_connection():
    """Check Redis connection"""
    print("\n🔍 Checking Redis Connection...")
    
    try:
        from django.conf import settings
        import redis
        
        redis_url = getattr(settings, 'CELERY_BROKER_URL', None)
        if not redis_url:
            print("❌ No Redis URL configured")
            return False
        
        print(f"✅ Redis URL: {redis_url}")
        
        # Try to connect to Redis
        r = redis.from_url(redis_url)
        r.ping()
        print("✅ Redis connection successful")
        
        # Check Redis info
        info = r.info()
        print(f"✅ Redis version: {info.get('redis_version', 'Unknown')}")
        print(f"✅ Connected clients: {info.get('connected_clients', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def check_email_settings():
    """Check email settings"""
    print("\n🔍 Checking Email Settings...")
    
    try:
        from django.conf import settings
        
        print(f"✅ Email backend: {getattr(settings, 'EMAIL_BACKEND', 'Not set')}")
        print(f"✅ Email host: {getattr(settings, 'EMAIL_HOST', 'Not set')}")
        print(f"✅ Email port: {getattr(settings, 'EMAIL_PORT', 'Not set')}")
        print(f"✅ Email user: {getattr(settings, 'EMAIL_HOST_USER', 'Not set')}")
        print(f"✅ Default from: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'Not set')}")
        
        # Check if email settings are complete
        if all([
            getattr(settings, 'EMAIL_HOST', None),
            getattr(settings, 'EMAIL_HOST_USER', None),
            getattr(settings, 'EMAIL_HOST_PASSWORD', None)
        ]):
            print("✅ Email settings are complete")
            return True
        else:
            print("❌ Email settings are incomplete")
            return False
            
    except Exception as e:
        print(f"❌ Error checking email settings: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Celery Worker Check")
    print("=" * 50)
    
    # Check Redis
    redis_ok = check_redis_connection()
    
    # Check workers
    workers_ok = check_celery_workers()
    
    # Check email settings
    email_ok = check_email_settings()
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    print(f"Redis Connection: {'✅ OK' if redis_ok else '❌ FAILED'}")
    print(f"Celery Workers: {'✅ OK' if workers_ok else '❌ FAILED'}")
    print(f"Email Settings: {'✅ OK' if email_ok else '❌ FAILED'}")
    
    if all([redis_ok, workers_ok, email_ok]):
        print("\n🎉 All systems are running!")
        print("✅ Celery workers are active")
        print("✅ Redis is connected")
        print("✅ Email settings are configured")
    else:
        print("\n💥 Issues detected!")
        if not redis_ok:
            print("❌ Redis connection failed - check Redis server")
        if not workers_ok:
            print("❌ Celery workers not running - start workers with:")
            print("   celery -A courseapp worker -l info")
        if not email_ok:
            print("❌ Email settings incomplete - check environment variables") 