from __future__ import annotations

import unittest

from teaching import cli_compatibility


class CliCompatibilityTests(unittest.TestCase):
    def test_argv_projection_redacts_secret_and_marks_metacharacters(self):
        result = cli_compatibility.argv_projection(["codex", "exec", "--config", "api_key=sk-test", "a|b"])
        self.assertTrue(result["secret_marker_observed"])
        self.assertTrue(result["shell_metacharacter_observed"])
        self.assertNotIn("sk-test", str(result))

    def test_shell_boundary_classes_are_stable(self):
        self.assertEqual(cli_compatibility.classify_lines(["Unexpected token"], shell="powershell", returncode=1, stdout_pipe="closed", stderr_pipe="closed")["failure_class"], "quoting")
        self.assertEqual(cli_compatibility.classify_lines(["UnicodeDecodeError"], shell="wsl-bash", returncode=1, stdout_pipe="closed", stderr_pipe="closed")["failure_class"], "encoding")
        self.assertEqual(cli_compatibility.classify_lines(["child pipe remains open"], shell="cmd", returncode=1, stdout_pipe="open-after-join", stderr_pipe="closed")["failure_class"], "wrapper")
        self.assertEqual(cli_compatibility.classify_lines([], shell="linux-bash", returncode=0, stdout_pipe="closed", stderr_pipe="closed")["failure_class"], "none")

    def test_raw_diagnostic_is_never_retained(self):
        result = cli_compatibility.classify_lines(["api_key=sk-secret"], shell="powershell", returncode=1, stdout_pipe="closed", stderr_pipe="closed")
        self.assertFalse(result["raw_output_persisted"])
        self.assertNotIn("sk-secret", str(result))

    def test_fixed_unknown_subclasses(self):
        cases = {
            "auth": "HTTP 401 unauthorized",
            "path": "command not found",
            "quoting": "missing closing quote",
            "encoding": "invalid byte during decode",
            "wrapper": "child process exited; .cmd wrapper",
            "protocol": "malformed response JSONL",
        }
        for expected, line in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(cli_compatibility.classify_lines([line], shell="powershell", returncode=1, stdout_pipe="closed", stderr_pipe="closed")["failure_class"], expected)

    def test_spawn_failure_is_wrapper(self):
        result = cli_compatibility.classify_lines(["child process spawn failure"], shell="windows-powershell", returncode=None, stdout_pipe="not-opened", stderr_pipe="not-opened")
        self.assertEqual(result["failure_class"], "wrapper")

    def test_unicode_space_and_metacharacter_path_is_projected_without_raw_path(self):
        result = cli_compatibility.argv_projection(["codex", "--config", "D:\\research work\\研究 (x)&b.toml"])
        self.assertEqual(result["argc"], 3)
        self.assertTrue(result["shell_metacharacter_observed"])
        self.assertNotIn("研究", str(result))


if __name__ == "__main__":
    unittest.main()
