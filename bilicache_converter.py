#!/usr/bin/env python3
"""Remux one Bilibili desktop download into a standard MP4."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


class ConversionError(Exception):
    """A problem the user can fix without a traceback."""


def find_tool(name: str) -> str:
    for candidate in (shutil.which(name), f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if candidate and Path(candidate).is_file():
            return candidate
    raise ConversionError(f"找不到 {name}。请先安装 FFmpeg（需要 ffmpeg 和 ffprobe）。")


def m4s_offset(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(32)
    if header[:9] == b"000000000" and header[13:17] == b"ftyp":
        return 9
    if header[4:8] == b"ftyp":
        return 0
    raise ConversionError(f"不是受支持的 MP4/M4S 缓存文件：{path.name}")


def inspect_media(path: Path, ffprobe: str, offset: int = 0) -> dict:
    command = [
        ffprobe, "-v", "error", "-f", "mov", "-skip_initial_bytes", str(offset),
        "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
        raise ConversionError(f"无法读取 {path.name}：{detail}")
    return json.loads(result.stdout)


def media_types(info: dict) -> set[str]:
    return {stream.get("codec_type", "") for stream in info.get("streams", [])}


def episode_files(source: Path, ffprobe: str) -> tuple[Path, tuple[Path, int, dict], tuple[Path, int, dict]]:
    if not source.exists():
        raise ConversionError(f"找不到输入路径：{source}")
    folder = source if source.is_dir() else source.parent
    if not folder.is_dir():
        raise ConversionError(f"找不到文件夹：{folder}")
    if source.is_file() and source.suffix.lower() != ".m4s":
        raise ConversionError("请选择一集的文件夹，或其中一个 .m4s 文件。")
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".m4s")
    if len(files) != 2:
        raise ConversionError(f"{folder.name} 中找到 {len(files)} 个 .m4s 文件；每集需要恰好两个。")
    checked = [(p, m4s_offset(p)) for p in files]
    inspected = [(p, offset, inspect_media(p, ffprobe, offset)) for p, offset in checked]
    videos = [item for item in inspected if media_types(item[2]) == {"video"}]
    audios = [item for item in inspected if media_types(item[2]) == {"audio"}]
    if len(videos) != 1 or len(audios) != 1:
        raise ConversionError("无法确定唯一的视频文件和音频文件；请确认它们属于同一集。")
    return folder, videos[0], audios[0]


def episode_title(folder: Path) -> str:
    info_file = folder / "videoInfo.json"
    if info_file.is_file():
        try:
            title = json.loads(info_file.read_text(encoding="utf-8")).get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()
        except (OSError, ValueError):
            pass
    return folder.name


def safe_filename(title: str, folder_name: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title)
    clean = re.sub(r"\s+", " ", clean).strip(" .")[:100].rstrip(" .")
    return f"{clean or folder_name}-{folder_name}.mp4"


def duration(info: dict) -> float:
    try:
        return float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        return 0.0


def convert(source: Path, output: Path | None, output_dir: Path | None, overwrite: bool) -> Path:
    ffprobe, ffmpeg = find_tool("ffprobe"), find_tool("ffmpeg")
    folder, video, audio = episode_files(source, ffprobe)

    if output is None:
        target_dir = output_dir or folder
        target_dir.mkdir(parents=True, exist_ok=True)
        output = target_dir / safe_filename(episode_title(folder), folder.name)
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".mp4":
        raise ConversionError("输出文件名必须以 .mp4 结尾。")
    if not output.parent.is_dir():
        raise ConversionError(f"输出文件夹不存在：{output.parent}")
    if output.exists() and not overwrite:
        raise ConversionError(f"输出文件已存在：{output}。如需替换，请加 --overwrite。")

    source_bytes = video[0].stat().st_size + audio[0].stat().st_size
    free_bytes = shutil.disk_usage(output.parent).free
    if free_bytes < source_bytes + 100_000_000:
        raise ConversionError(f"目标磁盘空间不足，转换这一集约需 {source_bytes / 1e9:.2f} GB。")

    partial = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.part.mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-stats", "-nostdin",
        "-f", "mov", "-skip_initial_bytes", str(video[1]), "-i", str(video[0]),
        "-f", "mov", "-skip_initial_bytes", str(audio[1]), "-i", str(audio[0]),
        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart",
        "-y", str(partial),
    ]
    print(f"标题：{episode_title(folder)}", flush=True)
    print(f"视频：{video[0].name}", flush=True)
    print(f"音频：{audio[0].name}", flush=True)
    print(f"输出：{output}", flush=True)
    try:
        result = subprocess.run(command)
        if result.returncode:
            raise ConversionError("FFmpeg 合并失败；源文件可能不完整。")
        result_info = inspect_media(partial, ffprobe)
        if not {"video", "audio"}.issubset(media_types(result_info)):
            raise ConversionError("生成的 MP4 缺少画面或声音。")
        expected = max(duration(video[2]), duration(audio[2]))
        if expected and duration(result_info) < expected - max(2, expected * 0.01):
            raise ConversionError("生成的 MP4 时长异常，已取消输出。")
        if output.exists() and not overwrite:
            raise ConversionError(f"转换期间目标文件已出现：{output}。")
        os.replace(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BiliCache Converter：把一集 Bilibili 桌面下载缓存无损封装为 MP4。")
    parser.add_argument("source", type=Path, help="一集的下载文件夹，或其中一个 .m4s 文件")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("-o", "--output", type=Path, help="指定输出 MP4 文件")
    target.add_argument("-d", "--output-dir", type=Path, help="指定输出文件夹")
    parser.add_argument("--overwrite", action="store_true", help="允许替换已有的输出 MP4")
    args = parser.parse_args(argv)
    try:
        result = convert(args.source.expanduser().resolve(), args.output, args.output_dir, args.overwrite)
    except (ConversionError, OSError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    print(f"完成：{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
