#!/usr/bin/env python3
"""
Neo4j Connection Verification Script

Run this to verify Neo4j is properly installed and accessible.
"""

import sys
from pathlib import Path

# Add workspace root to path
workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

def check_neo4j_connection():
    """Check if Neo4j is running and accessible."""
    print("\n" + "="*70)
    print("NEO4J CONNECTION VERIFICATION")
    print("="*70 + "\n")
    
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import ServiceUnavailable, AuthError
        print("[OK] neo4j-driver package installed")
    except ImportError as e:
        print(f"[ERROR] neo4j-driver not installed: {e}")
        print("\n   Install with: pip install neo4j")
        return False
    
    # Try to connect
    print("[WAIT] Attempting connection to bolt://localhost:7687...")
    try:
        driver = GraphDatabase.driver(
            'bolt://localhost:7687',
            auth=('neo4j', 'password'),
            connection_acquire_timeout=5
        )
        
        # Try a simple query
        with driver.session() as session:
            result = session.run('MATCH (n) RETURN COUNT(n) as count')
            record = result.single()
            count = record['count'] if record else 0
        
        driver.close()
        
        print("[OK] CONNECTION SUCCESSFUL\n")
        print(f"   URI:       bolt://localhost:7687")
        print(f"   Username:  neo4j")
        print(f"   Status:    RUNNING [OK]")
        print(f"   Nodes:     {count}")
        print(f"   Web UI:    http://localhost:7474\n")
        
        return True
        
    except ServiceUnavailable as e:
        print("[ERROR] CONNECTION FAILED\n")
        print(f"   Error: Neo4j is not running or not accessible")
        print(f"   Details: {e}\n")
        print("   SOLUTION:")
        print("   1. Start Neo4j using one of these methods:")
        print("      • Docker:     See docker-setup/ directory")
        print("      • Neo4j Desktop: https://neo4j.com/download/")
        print("      • Server:     https://neo4j.com/deployment/\n")
        return False
        
    except AuthError as e:
        print("[ERROR] AUTHENTICATION FAILED\n")
        print(f"   Error: Invalid credentials")
        print(f"   Details: {e}\n")
        print("   SOLUTION:")
        print("   Verify credentials are:")
        print("   • Username: neo4j")
        print("   • Password: password")
        print("   • Port: 7687\n")
        return False
        
    except Exception as e:
        print(f"[ERROR] UNEXPECTED ERROR\n")
        print(f"   {type(e).__name__}: {e}\n")
        return False


if __name__ == "__main__":
    success = check_neo4j_connection()
    sys.exit(0 if success else 1)
