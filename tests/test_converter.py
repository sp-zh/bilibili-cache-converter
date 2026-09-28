import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bilicache_converter.py"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
class ConverterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "123456789"
        self.folder.mkdir()
        video = self.folder / "video.mp4"
        audio = self.folder / "audio.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30",
            "-t", "1", "-an", "-c:v", "mpeg4", "-y", str(video),
        ], check=True)
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "1", "-vn", "-c:a", "aac", "-y", str(audio),
        ], check=True)
        for source, name in ((video, "part-video.m4s"), (audio, "part-audio.m4s")):
            (self.folder / name).write_bytes(b"000000000" + source.read_bytes())
            source.unlink()
        (self.folder / "videoInfo.json").write_text(json.dumps({"title": "测试：一集/课程"}))

    def run_converter(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.folder), *extra],
            capture_output=True, text=True,
        )

    def test_remux_and_protect_existing_output(self):
        first = self.run_converter()
        self.assertEqual(first.returncode, 0, first.stderr)
        output = self.folder / "测试：一集_课程-123456789.mp4"
        self.assertTrue(output.is_file())
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
            "-of", "json", str(output),
        ], check=True, capture_output=True, text=True)
        kinds = {stream["codec_type"] for stream in json.loads(result.stdout)["streams"]}
        self.assertEqual(kinds, {"video", "audio"})
        original_size = output.stat().st_size
        second = self.run_converter()
        self.assertEqual(second.returncode, 1)
        self.assertIn("已存在", second.stderr)
        self.assertEqual(output.stat().st_size, original_size)

        replaced = self.run_converter("--overwrite")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertEqual(output.stat().st_size, original_size)

    def test_standard_header_and_output_directory(self):
        for path in self.folder.glob("*.m4s"):
            path.write_bytes(path.read_bytes()[9:])
        output_dir = Path(self.temp.name) / "exports"
        result = self.run_converter("-d", str(output_dir))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((output_dir / "测试：一集_课程-123456789.mp4").is_file())


if __name__ == "__main__":
    unittest.main()
