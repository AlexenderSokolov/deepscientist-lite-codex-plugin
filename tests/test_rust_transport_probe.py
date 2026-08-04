import json
import unittest
from pathlib import Path
from unittest import mock

from teaching.rust_transport_probe import RustTransportProbeError, run_once, transport_signals


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeProcess:
    returncode = 1

    def communicate(self, timeout):
        return (
            '{"type":"thread.started"}\n{"type":"error","message":"provider stream disconnected"}\n{"type":"turn.failed"}\n',
            "",
        )


class _TerminalThenNonzeroProcess:
    returncode = 1

    def communicate(self, timeout):
        return ('{"type":"thread.started"}\n{"type":"turn.completed"}\n', "")


class RustTransportProbeTests(unittest.TestCase):
    def test_reduces_stream_disconnect_without_raw_output(self):
        output = REPO_ROOT / "unwritten-rust-transport-receipt.json"
        with (
            mock.patch("teaching.rust_transport_probe.subprocess.Popen", return_value=_FakeProcess()),
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(Path, "write_text", return_value=0) as write_text,
        ):
            receipt = run_once(codex_bin=Path(__file__), codex_home=REPO_ROOT, workspace=REPO_ROOT, output_path=output)
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["schema_version"], "ds-lite.cli-acceptance.v1")
        self.assertEqual(receipt["identity"], output.parent.name)
        self.assertRegex(receipt["binary_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["transport_signals"], ["stream-disconnect"])
        self.assertFalse(receipt["raw_output_persisted"])
        self.assertFalse(receipt["raw_error_text_persisted"])
        saved = write_text.call_args.args[0]
        self.assertNotIn("provider stream disconnected", saved)

    def test_resolves_child_paths_before_changing_workspace(self):
        output = REPO_ROOT / "unwritten-path-rust-receipt.json"
        with (
            mock.patch("teaching.rust_transport_probe.subprocess.Popen", return_value=_TerminalThenNonzeroProcess()) as popen,
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(Path, "write_text", return_value=0),
        ):
            run_once(codex_bin=Path(__file__), codex_home=".", workspace=".", output_path=output)
        self.assertTrue(Path(popen.call_args.kwargs["cwd"]).is_absolute())
        self.assertTrue(Path(popen.call_args.kwargs["env"]["CODEX_HOME"]).is_absolute())

    def test_refuses_to_overwrite_a_receipt(self):
        output = REPO_ROOT / "existing-rust-transport-receipt.json"
        with mock.patch.object(Path, "exists", return_value=True):
            with self.assertRaises(RustTransportProbeError):
                run_once(codex_bin=Path(__file__), codex_home=REPO_ROOT, workspace=REPO_ROOT, output_path=output)

    def test_accepts_terminal_turn_before_nonzero_background_exit(self):
        output = REPO_ROOT / "unwritten-terminal-rust-receipt.json"
        with (
            mock.patch("teaching.rust_transport_probe.subprocess.Popen", return_value=_TerminalThenNonzeroProcess()),
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch.object(Path, "write_text", return_value=0),
        ):
            receipt = run_once(codex_bin=Path(__file__), codex_home=REPO_ROOT, workspace=REPO_ROOT, output_path=output)
        self.assertEqual(receipt["status"], "passed")
        self.assertTrue(receipt["post_terminal_process_exit_nonzero"])

    def test_transport_signals_are_allow_listed(self):
        signals = transport_signals(["rustls certificate verify failed; ALPN h2", "proxy ignored"])
        self.assertEqual(signals, ["http2-or-alpn", "proxy", "tls"])


if __name__ == "__main__":
    unittest.main()
