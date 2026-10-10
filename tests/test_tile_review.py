#!/usr/bin/env python3
"""tile_review.py 测试。

用法：
    python3 tests/test_tile_review.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import tile_review as tr

PASS = 0
FAIL = 0
SCRIPT = REPO / "scripts" / "tile_review.py"
FORBIDDEN = ("#" + "6754C8", "san" + "ze", "叁" + "則")
REVIEW_FIELDS = (
    "size",
    "hasAlpha",
    "borderClear",
    "subjectSpan",
    "accentShare",
    "inkCore",
    "accentCore",
    "flags",
)


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: FAIL — {detail}")


def run_review(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


print("\n── 1. 技能正文不写站点值 ──")

static_files = [
    REPO / "references" / "tile-mode.md",
    REPO / "scripts" / "tile_review.py",
]
static_files.extend(path for path in (REPO / "assets" / "tile-styles").rglob("*") if path.is_file())
for path in static_files:
    body = path.read_text(encoding="utf-8")
    relative = path.relative_to(REPO)
    for needle in FORBIDDEN:
        check(f"{relative} 不含 {needle}", needle not in body, "found")

print("\n── 2. 文档里的阈值与脚本默认值一致 ──")

doc = (REPO / "references" / "tile-mode.md").read_text(encoding="utf-8")
for key, value in tr.DEFAULT_GATES.items():
    check(f"tile-mode.md 写出 {key}", f"{key}: {value}" in doc, f"missing {key}: {value}")


print("\n── 3. 缺少 --profile ──")

with tempfile.TemporaryDirectory() as raw_dir:
    result = run_review([raw_dir])
    check("缺少 --profile 退出 1", result.returncode == 1, f"code {result.returncode} {result.stderr}")
    check(
        "提示可以复制示例风格档",
        "examples/tile-style.example.json" in result.stderr,
        result.stderr,
    )


try:
    from PIL import Image
    from PIL import ImageDraw
except ImportError:
    print("\n── 4. 图片测试 ──")
    print("  ⚠️  未安装 Pillow，跳过图片测试。安装：pip install Pillow")
else:
    print("\n── 4. 对照图与 review.json ──")

    PAGE_LIGHT = (250, 250, 250)
    PAGE_DARK = (17, 17, 17)
    INK = (85, 85, 85, 255)
    ACCENT = (34, 102, 204, 255)
    PROFILE = {
        "palette": {
            "ink": "#555555",
            "accent": "#2266CC",
            "accent_name": "blue",
            "mat": {"light": "#FFFFFF", "dark": "#EEEEEE"},
            "paper": {"light": "#F6F6F6", "dark": "#E2E2E2"},
            "page": {"light": "#FAFAFA", "dark": "#111111"},
        },
        "sizes": [32, 16],
        "candidates": 2,
        "anchors": [],
    }

    def save_profile(directory):
        path = directory / "tile-style.json"
        path.write_text(json.dumps(PROFILE), encoding="utf-8")
        return path

    def normal_image():
        image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle([8, 8, 39, 39], outline=INK, width=8)
        draw.rectangle([22, 22, 25, 25], fill=ACCENT)
        return image

    def full_accent_image():
        return Image.new("RGBA", (48, 48), ACCENT)

    def anchor_image():
        image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([10, 10, 37, 37], fill=INK)
        return image

    def wide_runs(image, y0, y1, page, min_width=10):
        pixels = image.load()
        best = 0
        for y in range(y0, y1):
            runs = 0
            run = 0
            for x in range(image.size[0]):
                if pixels[x, y] != page:
                    run += 1
                else:
                    if run >= min_width:
                        runs += 1
                    run = 0
            if run >= min_width:
                runs += 1
            if runs > best:
                best = runs
        return best

    with tempfile.TemporaryDirectory() as raw_dir:
        directory = Path(raw_dir)
        profile = save_profile(directory)
        normal_image().save(directory / "cand-1.png")
        full_accent_image().save(directory / "cand-2.png")
        anchor = directory / "anchor.png"
        anchor_image().save(anchor)
        result = run_review([
            str(directory),
            "--profile",
            str(profile),
            "--anchors",
            str(anchor),
        ])
        check("对照脚本退出 0", result.returncode == 0, result.stderr)
        sheet_path = directory / "candidate-review.png"
        review_path = directory / "review.json"
        check("写出 candidate-review.png", sheet_path.is_file())
        check("写出 review.json", review_path.is_file())
        if sheet_path.is_file() and review_path.is_file():
            sheet = Image.open(sheet_path).convert("RGB")
            width, height = sheet.size
            top = wide_runs(sheet, 0, height // 2, PAGE_LIGHT)
            bottom = wide_runs(sheet, height // 2, height, PAGE_DARK)
            check("列数等于候选数加 anchors 数", top == 3 and bottom == 3, f"top {top} bottom {bottom}")
            check("浅色行在上", sheet.getpixel((0, 0)) == PAGE_LIGHT, str(sheet.getpixel((0, 0))))
            check("深色行在下", sheet.getpixel((0, height // 2)) == PAGE_DARK, str(sheet.getpixel((0, height // 2))))
            records = json.loads(review_path.read_text(encoding="utf-8"))
            check("每个候选一项", isinstance(records, list) and len(records) == 2, str(records)[:200])
            if isinstance(records, list) and len(records) == 2:
                for record in records:
                    missing = [field for field in REVIEW_FIELDS if field not in record]
                    check(f"{record.get('name')} 字段齐全", not missing, str(missing))
                by_name = {record["name"]: record for record in records}
                flags = by_name.get("cand-2", {}).get("flags", [])
                check("满幅强调色带 accent-too-large", "accent-too-large" in flags, str(flags))
                quiet = by_name.get("cand-1", {}).get("flags", [])
                check("正常图不带 accent-too-large", "accent-too-large" not in quiet, str(quiet))

    print("\n── 5. 读不到图片 ──")

    with tempfile.TemporaryDirectory() as raw_dir:
        directory = Path(raw_dir)
        profile = save_profile(directory)
        normal_image().save(directory / "cand-1.png")
        (directory / "cand-2.png").write_bytes(b"not a png")
        result = run_review([str(directory), "--profile", str(profile)])
        check("损坏的候选退出 2", result.returncode == 2, f"code {result.returncode} {result.stderr}")

    with tempfile.TemporaryDirectory() as raw_dir:
        directory = Path(raw_dir)
        profile = save_profile(directory)
        normal_image().save(directory / "cand-1.png")
        missing = directory / "missing-anchor.png"
        result = run_review([
            str(directory),
            "--profile",
            str(profile),
            "--anchors",
            str(missing),
        ])
        check("缺失的 anchor 退出 2", result.returncode == 2, f"code {result.returncode} {result.stderr}")


print(f"\n{'=' * 50}")
print(f"结果: {PASS} 通过, {FAIL} 失败 (共 {PASS + FAIL})")


import unittest


class ExistingOfflineChecks(unittest.TestCase):
    def test_checks_passed(self):
        self.assertEqual(FAIL, 0, f"{FAIL} of {PASS + FAIL} existing checks failed")


if __name__ == "__main__":
    sys.exit(1 if FAIL else 0)
