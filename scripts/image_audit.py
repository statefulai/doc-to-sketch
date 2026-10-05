#!/usr/bin/env python3
"""Local cap accounting and receipts for generate_image.sh (no API calls)."""

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def change_count(path: Path, delta: int, maximum=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as count_file:
        fcntl.flock(count_file, fcntl.LOCK_EX)
        count_file.seek(0)
        raw = count_file.read().strip()
        try:
            count = int(raw) if raw else 0
        except ValueError as exc:
            raise ValueError(f"计数文件无效: {path}") from exc
        if count < 0:
            raise ValueError(f"计数文件无效: {path}")
        if maximum is not None and count >= maximum:
            raise ValueError(f"无人值守生图上限 {maximum} 张已到达；本次调用已拒绝 ({path})")
        count = max(0, count + delta)
        count_file.seek(0)
        count_file.truncate()
        count_file.write(f"{count}\n")
        count_file.flush()
        os.fsync(count_file.fileno())


def required_text(path: str) -> list[str]:
    if not path:
        return []
    content = Path(path).read_text(encoding="utf-8")
    if content.lstrip().startswith("["):
        items = json.loads(content)
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ValueError("required_text JSON 必须是字符串数组")
        return items
    return [line.strip() for line in content.splitlines() if line.strip()]


def write_receipt(args: argparse.Namespace) -> None:
    image = Path(args.output_file)
    image_bytes = image.read_bytes()
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": args.mode,
        "model": args.model,
        "size": args.size,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "output_file": str(image.resolve()),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "bytes": len(image_bytes),
        "required_text": required_text(args.required_text_file),
        "review_status": "pending_cross_audit",
    }
    receipt_path = Path(args.output_dir) / "sketch-receipt.jsonl"
    line = (json.dumps(receipt, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reserve = commands.add_parser("reserve")
    reserve.add_argument("count_file", type=Path)
    reserve.add_argument("maximum", type=int)
    release = commands.add_parser("release")
    release.add_argument("count_file", type=Path)
    validate = commands.add_parser("validate-text")
    validate.add_argument("required_text_file")
    receipt = commands.add_parser("receipt")
    receipt.add_argument("--output-file", required=True)
    receipt.add_argument("--output-dir", required=True)
    receipt.add_argument("--mode", choices=("attended", "unattended"), required=True)
    receipt.add_argument("--model", required=True)
    receipt.add_argument("--size", required=True)
    prompt_group = receipt.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file")
    receipt.add_argument("--required-text-file", default="")
    args = parser.parse_args()
    try:
        if args.command == "reserve":
            change_count(args.count_file, 1, args.maximum)
        elif args.command == "release":
            change_count(args.count_file, -1)
        elif args.command == "validate-text":
            required_text(args.required_text_file)
        else:
            write_receipt(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
