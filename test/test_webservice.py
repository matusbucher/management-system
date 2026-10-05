import sys
import time
from pathlib import Path

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.etl.webservice import WebserviceAPI

RATE_LIMIT_DELAY = 1

NIS2_CELEX = "32022L2555"
DORA_CELEX = "32022R2554"
CRA_CELEX = "32024R2847"


def test_single_celex():
    """Test searching for a single document by CELEX number."""
    print("=" * 80)
    print("TEST 1: Search by Single CELEX Number")
    print("=" * 80)
    
    try:
        webservice = WebserviceAPI()
        celex = NIS2_CELEX  # NIS2 Directive
        
        print(f"\n[SEARCH] Searching for: {celex}")
        references = webservice.search_by_celex(celex, page_size=10)
        
        if references:
            print(f"[OK] Found {len(references)} result(s)")
            print(f"   First reference: {references[0][:50]}")
            return True
        else:
            print("[WARNING]  No results found")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        return False


def test_multiple_celex():
    """Test searching for multiple documents by CELEX numbers."""
    print("\n" + "=" * 80)
    print("TEST 2: Search by Multiple CELEX Numbers")
    print("=" * 80)
    
    try:
        webservice = WebserviceAPI()
        celex_list = [NIS2_CELEX, DORA_CELEX, CRA_CELEX]
        names = ["NIS2", "DORA", "CRA"]
        
        print(f"\n[SEARCH] Searching for: {', '.join(names)}")
        references = webservice.search_by_celex(celex_list, page_size=10)
        
        if references:
            print(f"[OK] Found {len(references)} result(s)")
            for i, ref in enumerate(references):
                print(f"   {i+1}. {ref[:50]}")
            return True
        else:
            print("[WARNING]  No results found")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        return False


def test_expert_query():
    """Test searching with expert query format."""
    print("\n" + "=" * 80)
    print("TEST 3: Expert Query Format")
    print("=" * 80)
    
    try:
        webservice = WebserviceAPI()
        query = 'DN="32022L2555"'
        
        print(f"\n[SEARCH] Expert query: {query}")
        references = webservice.search(query, page_size=10)
        
        if references:
            print(f"[OK] Found {len(references)} result(s)")
            print(f"   First reference: {references[0][:50]}")
            return True
        else:
            print("[WARNING]  No results found")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        return False


def test_pagination():
    """Test pagination with page and page_size parameters."""
    print("\n" + "=" * 80)
    print("TEST 4: Pagination")
    print("=" * 80)
    
    try:
        webservice = WebserviceAPI()
        celex = "32022*"
        
        print(f"\n[SEARCH] Searching with pagination (page=1, page_size=10)")
        refs_page1 = webservice.search_by_celex(celex, page=1, page_size=10)
        
        if refs_page1:
            print(f"[OK] Page 1: Found {len(refs_page1)} result(s)")
            for i, ref in enumerate(refs_page1):
                print(f"   {i+1}. {ref[:50]}")
            return True
        else:
            print("[WARNING]  No results found")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error: {str(e)}")
        return False


def main():
    print("\nWebserviceAPI Test Suite")
    print("=" * 80)
    
    tests = [
        ("Single CELEX", test_single_celex),
        ("Multiple CELEX", test_multiple_celex),
        ("Expert Query", test_expert_query),
        ("Pagination", test_pagination),
    ]

    results = []
    for test_name, test_func in tests:
        result = test_func()
        results.append((test_name, result))
        # Add delay between tests to prevent server spam
        if test_func != tests[-1][1]:
            time.sleep(RATE_LIMIT_DELAY)
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    passed = sum(1 for _, v in results if v)
    total = len(results)

    for test_name, passed_test in results:
        status = "[OK] PASS" if passed_test else "[ERROR] FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 80)
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    main()
