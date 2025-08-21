#!/usr/bin/env python3
"""
Test MySQL client installation
"""

def test_mysql_client():
    """Test if MySQL client can be imported"""
    try:
        import MySQLdb
        print("✅ MySQL client imported successfully")
        return True
    except ImportError as e:
        print(f"❌ MySQL client import failed: {e}")
        return False

if __name__ == "__main__":
    test_mysql_client() 