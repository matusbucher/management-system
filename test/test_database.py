import unittest

import sys
from pathlib import Path

workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from src.database.database import Neo4jDatabase


class TestNeo4jDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Neo4jDatabase()

    def tearDown(self):
        self.db.close()

    def test_verify_connection(self):
        try:
            self.db.verify_connection()
        except Exception as e:
            self.fail(f"verify_connection() raised an exception: {e}")


if __name__ == "__main__":
    unittest.main()