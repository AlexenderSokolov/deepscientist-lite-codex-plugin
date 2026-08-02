import unittest
from pathlib import Path

from tools.validation.install_locked_dependencies import read_pins


class CiDependencyTests(unittest.TestCase):
    def test_controller_lock_is_pinned_and_hash_lines_are_parsed(self):
        root = Path(__file__).resolve().parents[1]
        pins = read_pins(root / "plugins" / "deepscientist-lite-core" / "controller" / "requirements.lock")
        self.assertGreaterEqual(len(pins), 10)
        self.assertEqual(pins[0], ("dbos", "2.29.0"))
        self.assertTrue(all(version and " " not in version for _, version in pins))


if __name__ == "__main__":
    unittest.main()
