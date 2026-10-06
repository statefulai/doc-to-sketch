#!/usr/bin/env python3
"""Local cap accounting and receipts for generate_image.sh (no API calls)."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def read_count(count_file, path: Path) -> int:
    count_file.seek(0)
    raw = count_file.read().strip()
    try:
        count = int(raw) if raw else 0
    except ValueError as exc:
        raise ValueError(f"计数文件无效: {path}") from exc
    if count < 0:
        raise ValueError(f"计数文件无效: {path}")
    return count


def write_count(count_file, count: int) -> None:
    count_file.seek(0)
    count_file.truncate()
    count_file.write(f"{count}\n")
    count_file.flush()
    os.fsync(count_file.fileno())


def lease_path(path: Path) -> Path:
    return path.with_name(path.name + ".leases.json")


def read_leases(path: Path) -> dict:
    ledger = lease_path(path)
    if not ledger.exists():
        return {}
    leases = json.loads(ledger.read_text(encoding="utf-8"))
    if not isinstance(leases, dict):
        raise ValueError(f"租约记录无效: {ledger}")
    return leases


def write_leases(path: Path, leases: dict) -> None:
    ledger = lease_path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=ledger.name + ".", delete=False) as output:
            temporary = Path(output.name)
            json.dump(leases, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, ledger)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reserve_slot(path: Path, maximum: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as count_file:
        fcntl.flock(count_file, fcntl.LOCK_EX)
        count = read_count(count_file, path)
        if maximum < 1:
            raise ValueError("图片上限必须是正整数")
        if count >= maximum:
            raise ValueError(f"无人值守生图上限 {maximum} 张已到达；本次调用已拒绝 ({path})")
        leases = read_leases(path)
        lease = f"{os.getpid()}-{secrets.token_hex(16)}"
        write_count(count_file, count + 1)
        leases[lease] = "reserved"
        write_leases(path, leases)
        return lease


def release_slot(path: Path, lease: str) -> None:
    with path.open("r+", encoding="utf-8") as count_file:
        fcntl.flock(count_file, fcntl.LOCK_EX)
        count = read_count(count_file, path)
        leases = read_leases(path)
        if leases.get(lease) != "reserved":
            raise ValueError("无效或已释放的租约")
        if count == 0:
            raise ValueError(f"计数文件无效: {path}")
        leases[lease] = "released"
        write_leases(path, leases)
        write_count(count_file, count - 1)


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
    relative_image = image.resolve().relative_to(Path(args.output_dir).resolve())
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": args.mode,
        "model": args.model,
        "size": args.size,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "output_file": str(relative_image),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "bytes": len(image_bytes),
        "required_text": required_text(args.required_text_file),
        "review_status": "pending_cross_audit",
    }
    receipt_path = Path(args.output_dir) / "sketch-receipt.jsonl"
    line = (json.dumps(receipt, ensure_ascii=False) + "\n").encode("utf-8")
    with receipt_path.open("ab") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(line)
        output.flush()
        os.fsync(output.fileno())


def write_review(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", args.image_sha256):
        raise ValueError("image_sha256 必须是 64 位小写十六进制字符串")
    if not args.reviewer.strip():
        raise ValueError("reviewer 不能为空")
    if args.verdict == "rejected" and not args.reason:
        raise ValueError("rejected 必须提供至少一条 --reason")
    output_dir = Path(args.output_dir)
    with (output_dir / "sketch-receipt.jsonl").open("rb") as receipts:
        fcntl.flock(receipts, fcntl.LOCK_SH)
        found = any(json.loads(line)["image_sha256"] == args.image_sha256
                    for line in receipts if line.strip())
    if not found:
        raise ValueError("image_sha256 在回执中不存在，不能写入审计结论")
    review = {
        "image_sha256": args.image_sha256,
        "verdict": args.verdict,
        "reasons": args.reason,
        "reviewer": args.reviewer,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    line = (json.dumps(review, ensure_ascii=False) + "\n").encode("utf-8")
    with (output_dir / "sketch-review.jsonl").open("ab") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(line)
        output.flush()
        os.fsync(output.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reserve = commands.add_parser("reserve")
    reserve.add_argument("count_file", type=Path)
    reserve.add_argument("maximum", type=int)
    release = commands.add_parser("release")
    release.add_argument("count_file", type=Path)
    release.add_argument("lease")
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
    review = commands.add_parser("review")
    review.add_argument("--output-dir", required=True)
    review.add_argument("--image-sha256", required=True)
    review.add_argument("--verdict", choices=("accepted", "rejected"), required=True)
    review.add_argument("--reason", action="append", default=[])
    review.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    try:
        if args.command == "reserve":
            print(reserve_slot(args.count_file, args.maximum))
        elif args.command == "release":
            release_slot(args.count_file, args.lease)
        elif args.command == "validate-text":
            required_text(args.required_text_file)
        elif args.command == "receipt":
            write_receipt(args)
        else:
            write_review(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
