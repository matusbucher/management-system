import sys
import time
import unittest
from pathlib import Path

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.eurlex.webservice_api import WebserviceAPI

RATE_LIMIT_DELAY = 1

NIS2_CELEX = "32022L2555"
DORA_CELEX = "32022R2554"
CRA_CELEX = "32024R2847"


class TestWebserviceAPI(unittest.TestCase):
    """Integration tests for the WebserviceAPI."""
    
    _has_run_test = None

    def setUp(self):
        # Keep a delay between requests to avoid exceeding the service rate limit.
        if getattr(self.__class__, "_has_run_test", False):
            time.sleep(RATE_LIMIT_DELAY)
        self.__class__._has_run_test = True

    def test_single_celex(self):
        """Test searching for a single document by CELEX number."""
        references = WebserviceAPI().search_by_celex(NIS2_CELEX, page_size=10)
        self.assertTrue(references, "No results found for the CELEX number")

    def test_multiple_celex(self):
        """Test searching for multiple documents by CELEX numbers."""
        celex_list = [NIS2_CELEX, DORA_CELEX, CRA_CELEX]
        references = WebserviceAPI().search_by_celex(celex_list, page_size=10)
        self.assertTrue(references, "No results found for the CELEX numbers")

    def test_expert_query(self):
        """Test searching with expert query format."""
        references = WebserviceAPI().search('DN="32022L2555"', page_size=10)
        self.assertTrue(references, "No results found for the expert query")

    def test_pagination(self):
        """Test pagination with page and page_size parameters."""
        references = WebserviceAPI().search_by_celex(
            "32022*", page=1, page_size=10
        )
        self.assertTrue(references, "No results found on page 1")


if __name__ == "__main__":
    unittest.main()
