# BiliCache Converter

将 **一集 Bilibili 桌面客户端下载缓存**转换为普通 MP4。程序识别该集文件夹中的视频和音频 `.m4s`，去除缓存文件头后用 FFmpeg 合并；不重新编码，原始文件保持不变。

## 支持的文件结构

```text
一集的文件夹/
├── 123456789-1-30080.m4s     # 视频流
├── 123456789-1-30280.m4s     # 音频流
└── videoInfo.json             # 可选，用于输出文件名
```

本工具面向上述 **每集两个 `.m4s` 文件**的离线下载结构。它支持 Bilibili 在 MP4 数据前添加的 9 字节缓存头，也接受标准 MP4 文件头。它不会下载视频、处理 DRM，或批量转换整个下载库。

## 环境要求

- macOS、Linux 或 Windows
- Python 3.10 或更新版本
- FFmpeg，且 `ffmpeg` 和 `ffprobe` 在 `PATH` 中；macOS 也会检查常见 Homebrew 路径

macOS 安装 FFmpeg 的常见命令是 `brew install ffmpeg`。程序只使用 Python 标准库，没有额外 Python 依赖。

## 使用方法

### Mac 图形入口

双击 [`BiliCache Converter.command`](./BiliCache%20Converter.command)，在弹出的文件夹选择窗口中选中 **某一集** 的文件夹。转换完成后，MP4 默认保存在该文件夹中。首次运行 `.command` 文件时，macOS 可能要求你在 Finder 中右键选择“打开”。

### 命令行

```sh
python3 bilicache_converter.py '/path/to/episode-folder'
python3 bilicache_converter.py '/path/to/episode-folder/video.m4s' -o '/path/to/lesson.mp4'
python3 bilicache_converter.py '/path/to/episode-folder' -d '/path/to/output-folder'
```

默认文件名来自 `videoInfo.json` 中的标题，并附加文件夹编号以避免重名。已有输出不会被覆盖；明确需要替换时添加 `--overwrite`。转换先写入临时 MP4，检查画面、声音和时长后再放到目标路径。中断或失败时会清理临时文件。

## 常见问题

**为什么不能把 `.m4s` 直接改名为 `.mp4`？** 缓存前有额外文件头，而且画面与声音分开存放。改名不会合并它们。

**会损失画质吗？** 不会。FFmpeg 使用 `-c copy` 封装现有流，不重新编码。

**需要多少空间？** 目标磁盘应至少留出与这一集音视频缓存总大小相近的空间；程序会在开始前检查。

**能转换所有 Bilibili 下载吗？** 不能保证。其他客户端版本、加密或不同目录结构可能需要不同处理方式。遇到不支持的格式时，程序会提示错误，不会修改源文件。

## 开发验证

运行 `python3 -m unittest discover -s tests -v`。测试用 FFmpeg 生成小型音视频样本，验证缓存头识别、流合并、输出检查和防覆盖行为。
