"""Download YouTube videos as MP3 files using yt-dlp.

Usage:
    python youtube_mp3.py <url> [url2] [url3] ...
    python youtube_mp3.py                          # prompts for URL

Requires: pip install yt-dlp
Optional: ffmpeg in PATH for best audio quality
"""

import subprocess
import sys
import os

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")


def download(url, output_dir=None, playlist=False):
    dest = output_dir or OUTPUT_DIR
    os.makedirs(dest, exist_ok=True)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x",                           # extract audio
        "--audio-format", "mp3",        # convert to mp3
        "--audio-quality", "0",         # best quality (VBR ~245kbps)
        "-o", os.path.join(dest, "%(title)s.%(ext)s"),
    ]
    if not playlist:
        cmd.append("--no-playlist")
    else:
        cmd.append("--yes-playlist")
    cmd.append(url)
    print(f"Downloading: {url}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print(f"Done! Saved to: {OUTPUT_DIR}")
    else:
        print(f"Failed with exit code {result.returncode}")
    return result.returncode


def main():
    urls = sys.argv[1:]
    if not urls:
        url = input("YouTube URL: ").strip()
        if not url:
            print("No URL provided.")
            return
        urls = [url]

    for url in urls:
        download(url)


if __name__ == "__main__":
    main()
