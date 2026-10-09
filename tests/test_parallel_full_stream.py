"""Exercise the shared HLS integration without network or GPU dependencies."""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


class ParallelFullStreamTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "src/aniworld/models/common/common.py"
        module = ast.parse(source.read_text())
        function = next(
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "_download_full_stream"
        )
        self.hls = types.ModuleType("hls_test_package.hls")
        self.hls.cleanup_temp_files = Mock()
        self.ffmpeg = MagicMock()
        self.parallel = Mock(return_value=(Path("video.ts"), None))
        self.run = Mock()
        self.manual = Mock()
        self.unsupported = type("Unsupported", (Exception,), {})
        self.namespace = {
            "__package__": "hls_test_package",
            "ffmpeg": self.ffmpeg,
            "_hls_rendition_download": self.parallel,
            "_run_ffmpeg_with_progress": self.run,
            "_download_hls_manual": self.manual,
            "_HLSManualUnsupported": self.unsupported,
            "logger": Mock(),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), self.namespace)
        self.module_patch = patch.dict(sys.modules, {"hls_test_package.hls": self.hls})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def download(self, url="https://example.test/master.m3u8?token=x"):
        self.namespace["_download_full_stream"](
            url, Path("episode.temp_full.mkv"), {"reconnect": 1},
            {"Referer": "https://example.test"},
            {"metadata:s:a:0": "language=deu"}, "h264_qsv", "episode", "deu",
        )

    def test_muxed_hls_encodes_local_file_and_cleans_up(self):
        self.download()
        self.ffmpeg.input.assert_called_once_with("video.ts")
        self.parallel.assert_called_once_with(
            "https://example.test/master.m3u8?token=x",
            Path("episode.temp_full.parallel_hls"),
            {"Referer": "https://example.test"}, "deu", "episode",
        )
        self.manual.assert_not_called()
        self.hls.cleanup_temp_files.assert_called_once()

    def test_separate_audio_is_explicitly_mapped(self):
        self.parallel.return_value = (Path("video.ts"), Path("audio.ts"))
        self.download()
        self.assertEqual(self.ffmpeg.input.call_count, 2)
        self.ffmpeg.output.assert_called_once()
        self.assertEqual(self.ffmpeg.output.call_args.kwargs["acodec"], "copy")
        self.assertEqual(self.ffmpeg.output.call_args.kwargs["metadata:s:a:0"], "language=deu")

    def test_unsupported_hls_keeps_remote_fallback(self):
        self.parallel.return_value = None
        self.manual.side_effect = self.unsupported("encrypted playlist")
        self.download()
        self.ffmpeg.input.assert_called_once_with(
            "https://example.test/master.m3u8?token=x", reconnect=1,
        )

    def test_encoding_failure_cleans_up_and_propagates(self):
        self.run.side_effect = RuntimeError("encoder failed")
        with self.assertRaisesRegex(RuntimeError, "encoder failed"):
            self.download()
        self.hls.cleanup_temp_files.assert_called_once()
        self.manual.assert_not_called()

    def test_non_hls_is_unchanged(self):
        self.download("https://example.test/video.mp4")
        self.parallel.assert_not_called()
        self.ffmpeg.input.assert_called_once_with("https://example.test/video.mp4", reconnect=1)

    def test_transfer_error_propagates(self):
        self.parallel.side_effect = RuntimeError("segment failed")
        with self.assertRaisesRegex(RuntimeError, "segment failed"):
            self.download()
        self.run.assert_not_called()
        self.manual.assert_not_called()


if __name__ == "__main__":
    unittest.main()
