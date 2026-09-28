#!/usr/bin/env python3
"""PyMedia Downloader — interactive CLI."""
import os
import sys
import subprocess
from pathlib import Path

from core import downloader
from core.utils import VIDEOS_DIR, AUDIO_DIR, IMAGES_DIR


def _print_banner():
    print(r"""
   ___        __  __          _ _         ___                    _                 
  | _ \_  _  |  \/  |___ __ _| (_)__ _   |   \ _____ __ ___ _ __ | |___ _ _ _ _ 
  |  _/ || | | |\/| / -_) _` | | / _` |  | |) / _ \ V  V / ' \| / / -_) '_| '_|
  |_|  \_, | |_|  |_\___\__,_|_|_\__,_|  |___/\___/\_/\_/|_|_|_\_\___|_| |_|  
       |__/                                                                       
    """)


def _menu():
    print("\nPyMedia Downloader v1.0\n")
    print("  1. Download video")
    print("  2. Download audio (extract from video)")
    print("  3. Download image")
    print("  4. Quit\n")


def _ask_quality(kind):
    if kind == "video":
        print("\nQuality:")
        print("  1. 360p    2. 480p    3. 720p    4. 1080p")
        print("  5. 2K      6. 4K      7. Best")
        q = input("Choice [4]: ").strip() or "4"
        return {"1": "360p", "2": "480p", "3": "720p",
                "4": "1080p", "5": "2k", "6": "4k", "7": "best"}.get(q, "1080p")
    if kind == "audio":
        print("\nBitrate:")
        print("  1. 128 kbps   2. 192 kbps   3. 320 kbps")
        q = input("Choice [2]: ").strip() or "2"
        return {"1": "128", "2": "192", "3": "320"}.get(q, "192")
    if kind == "image":
        print("\nSize:")
        print("  1. Original   2. 1280px   3. 1920px   4. 2560px   5. 3840px")
        q = input("Choice [1]: ").strip() or "1"
        return {"1": "original", "2": "720p", "3": "1080p",
                "4": "2k", "5": "4k"}.get(q, "original")
    return ""


def _ask_format(kind):
    if kind == "video":
        return (input("Format [mp4]: ").strip() or "mp4")
    if kind == "audio":
        return (input("Format [mp3]: ").strip() or "mp3")
    if kind == "image":
        return (input("Format (blank = keep original): ").strip())
    return ""


def main():
    _print_banner()
    while True:
        _menu()
        choice = input("Choice: ").strip()
        if choice == "4":
            print("Goodbye.")
            return
        if choice not in ("1", "2", "3"):
            print("Invalid choice.")
            continue

        kind = {"1": "video", "2": "audio", "3": "image"}[choice]
        url = input("\nURL: ").strip()
        if not url.startswith(("http://", "https://")):
            print("Invalid URL.")
            continue

        quality = _ask_quality(kind)
        fmt = _ask_format(kind)

        job = downloader.start_job(url, kind=kind, quality=quality, fmt=fmt)

        # Wait for completion, showing progress
        import time
        last = ""
        while True:
            time.sleep(0.4)
            info = downloader.get_job(job["id"])
            if not info:
                break
            line = (
                f"\r[{info['status']}] "
                f"{info['percent']:5.1f}%  "
                f"{info['speed']:<12} "
                f"ETA {info['eta']:<8}"
            )
            if line != last:
                print(line, end="", flush=True)
                last = line
            if info["status"] in ("done", "error"):
                print()
                break

        info = downloader.get_job(job["id"])
        if info["status"] == "done":
            print(f"✅ Saved: {info['file_path']}")
        else:
            print(f"❌ Failed: {info['error']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
