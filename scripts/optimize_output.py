#!/usr/bin/env python3
"""Optimize generated page images for web delivery.

Converts PNG images to JPEG with configurable quality, or checks that
existing images meet size constraints. This is a post-processing step,
not part of the default generation pipeline.

Requires: Pillow (pip install Pillow)

Usage:
  # Convert all PNGs in output/ to JPEG ≤500KB
  python3 scripts/optimize_output.py output/

  # Dry-run: report which files exceed the threshold
  python3 scripts/optimize_output.py output/ --check-only

  # Custom quality and size limit
  python3 scripts/optimize_output.py output/ --quality 90 --max-kb 300

  # Keep original PNGs alongside JPEGs
  python3 scripts/optimize_output.py output/ --keep-originals
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def check_pillow():
    """Return True if Pillow is available, False otherwise."""
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def optimize_file(
    path: Path,
    quality: int,
    max_kb: int,
    keep_original: bool,
    dry_run: bool,
) -> dict:
    """Optimize a single image file. Returns a result dict."""
    from PIL import Image

    orig_kb = path.stat().st_size / 1024
    result = {
        "file": str(path),
        "original_kb": round(orig_kb, 1),
        "action": "skip",
    }

    if dry_run:
        result["action"] = "over" if orig_kb > max_kb else "ok"
        return result

    img = Image.open(path)

    # Handle transparency by compositing on white
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    jpg_path = path.with_suffix(".jpg")
    img.save(jpg_path, "JPEG", quality=quality, optimize=True)
    new_kb = jpg_path.stat().st_size / 1024

    result["output"] = str(jpg_path)
    result["optimized_kb"] = round(new_kb, 1)
    result["reduction"] = f"{(1 - new_kb / orig_kb) * 100:.0f}%"
    result["action"] = "converted"

    if not keep_original:
        path.unlink()
        result["action"] = "replaced"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Optimize generated page images for web delivery."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing PNG images to optimize",
    )
    parser.add_argument(
        "--quality", "-q",
        type=int,
        default=85,
        help="JPEG quality 1-100 (default: 85)",
    )
    parser.add_argument(
        "--max-kb",
        type=int,
        default=500,
        help="Target max file size in KB (default: 500)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only report oversized files, do not convert",
    )
    parser.add_argument(
        "--keep-originals",
        action="store_true",
        help="Keep original PNG files alongside new JPEGs",
    )
    parser.add_argument(
        "--glob",
        default="*.png",
        help="Glob pattern for source files (default: *.png)",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"错误: 目录不存在: {args.directory}")
        sys.exit(1)

    if not args.check_only and not check_pillow():
        print("错误: 需要安装 Pillow")
        print("      pip install Pillow")
        sys.exit(1)

    files = sorted(args.directory.glob(args.glob))
    if not files:
        print(f"未找到匹配 {args.glob} 的文件")
        sys.exit(0)

    results = []
    for f in files:
        if args.check_only:
            kb = f.stat().st_size / 1024
            status = "⚠️  OVER" if kb > args.max_kb else "✅ OK"
            print(f"  {status}  {kb:7.0f}KB  {f.name}")
            results.append({"over": kb > args.max_kb})
        else:
            r = optimize_file(f, args.quality, args.max_kb, args.keep_originals, False)
            action = r["action"]
            orig = r["original_kb"]
            opt = r.get("optimized_kb", orig)
            reduction = r.get("reduction", "—")
            out_name = Path(r.get("output", r["file"])).name
            print(f"  {orig:7.0f}KB → {opt:7.0f}KB ({reduction})  {out_name}")
            results.append(r)

    # Summary
    if args.check_only:
        over = sum(1 for r in results if r["over"])
        print(f"\n{len(results)} 文件, {over} 超过 {args.max_kb}KB")
        sys.exit(1 if over > 0 else 0)
    else:
        total_orig = sum(r["original_kb"] for r in results)
        total_opt = sum(r.get("optimized_kb", r["original_kb"]) for r in results)
        print(f"\n总计: {total_orig:.0f}KB → {total_opt:.0f}KB "
              f"({(1 - total_opt / total_orig) * 100:.0f}% 减少)")


if __name__ == "__main__":
    main()
