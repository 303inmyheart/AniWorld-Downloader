"""QSV command configuration without hardware or application imports."""
import ast
import os
import platform
import unittest
from pathlib import Path
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / "src/aniworld/models/common/common.py"
module = ast.parse(source.read_text())
function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "_configure_qsv_args")
namespace = {"os": os, "platform": platform}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
configure = namespace["_configure_qsv_args"]

class QSVTests(unittest.TestCase):
    def test_copy_and_other_encoders_are_unchanged(self):
        for codec in ("copy", "libx264", "h264_nvenc"):
            args = ["ffmpeg", "-i", "in.mkv", "-vcodec", codec, "out.mkv"]
            self.assertEqual(configure(args), args)

    def test_all_intel_encoders_get_output_options(self):
        for codec in ("h264_qsv", "hevc_qsv", "av1_qsv"):
            args = ["ffmpeg", "-i", "in.mkv", "-vcodec", codec, "out.mkv"]
            with patch.dict(os.environ, {"ANIWORLD_QSV_DEVICE": ""}):
                result = configure(args)
            self.assertEqual(result[-5:], ["-pix_fmt", "nv12", "-global_quality", "23", "out.mkv"])
            self.assertEqual(args[-1], "out.mkv")
            self.assertNotIn("-pix_fmt", args)

    def test_device_precedes_inputs(self):
        with patch.dict(os.environ, {"ANIWORLD_QSV_DEVICE": "/dev/dri/renderD128"}), patch.object(platform, "system", return_value="Linux"):
            result = configure(["ffmpeg", "-i", "in.mkv", "-vcodec", "h264_qsv", "out.mkv"])
        self.assertEqual(result[1:3], ["-init_hw_device", "qsv=aniworld:hw,child_device=/dev/dri/renderD128"])

    def test_explicit_options_are_preserved(self):
        args = ["ffmpeg", "-i", "in.mkv", "-vcodec", "h264_qsv", "-pix_fmt", "p010le", "-global_quality", "20", "out.mkv"]
        with patch.dict(os.environ, {"ANIWORLD_QSV_DEVICE": ""}):
            self.assertEqual(configure(args), args)

if __name__ == "__main__":
    unittest.main()
