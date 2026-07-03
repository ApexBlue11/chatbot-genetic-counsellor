import sys
sys.path.append('.')
import unittest
from unittest.mock import patch
from core.api_clients import query_pubmed

class TestSymptomCorrelation(unittest.TestCase):
    @patch('core.api_clients.requests.get')
    def test_literature_symptom_search(self, mock_get):
        # Mock API responses for search and summary
        mock_search_response = MagicMock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = {
            "esearchresult": {
                "idlist": ["12345"]
            }
        }
        
        mock_summary_response = MagicMock()
        mock_summary_response.status_code = 200
        mock_summary_response.json.return_value = {
            "result": {
                "12345": {
                    "title": "MTHFR mutations and neural tube defects",
                    "source": "J Gen",
                    "pubdate": "2020",
                    "authors": [{"name": "Smith J"}]
                }
            }
        }
        
        mock_get.side_effect = [mock_search_response, mock_summary_response]
        
        res = query_pubmed("MTHFR seizures")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["title"], "MTHFR mutations and neural tube defects")
        self.assertEqual(res[0]["pmid"], "12345")

from unittest.mock import MagicMock
if __name__ == "__main__":
    unittest.main()
