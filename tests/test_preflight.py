import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).resolve().parents[1] / "tools/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_hostname_drives_candidate_without_secret_access(self):
        with patch.object(preflight.socket, "gethostname", return_value="test-host"):
            result = preflight.inventory()
        self.assertEqual(result["proposed_hindsight_bank"], "test-host-cli")
        self.assertIn("Candidate only", result["bank_note"])
        self.assertNotIn("credential", result)

    def test_wsl_detection(self):
        with patch.object(preflight.platform, "system", return_value="Linux"), \
             patch.object(preflight.platform, "release", return_value="6.6-microsoft-standard"):
            self.assertTrue(preflight.inventory()["wsl_detected"])


if __name__ == "__main__":
    unittest.main()
