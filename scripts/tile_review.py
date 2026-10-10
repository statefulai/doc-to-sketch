#!/usr/bin/env python3
"""Build a contact sheet and mark file for list-tile candidates.

Reads cand-*.png plus optional anchor images. Colors, sizes, and
thresholds come from a site style profile. This script does not
generate images and does not use the network.

Requires: Pillow (pip install Pillow)

Usage:
  python3 scripts/tile_review.py output/tiles/<slug> --profile tile-style.json
  python3 scripts/tile_review.py output/tiles/<slug> --profile tile-style.json --anchors a.png b.png
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path


DEFAULT_GATES = {
    "border_band": 0.05,
    "border_alpha_max": 8,
    "border_clear_min": 0.995,
    "accent_distance": 60,
    "accent_share_max": 0.12,
    "ink_core_min": 6,
}

PAGE_MARGIN = 8
LABEL_GAP = 4
COL_GAP = 8
GROUP_GAP = 24

REQUIRED_COLORS = (
    "palette.ink",
    "palette.accent",
    "palette.mat.light",
    "palette.mat.dark",
    "palette.paper.light",
    "palette.paper.dark",
    "palette.page.light",
    "palette.page.dark",
)


class ProfileError(Exception):
    pass


class UnreadableImage(Exception):
    pass


def check_pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def parse_hex(value, field):
    if not isinstance(value, str):
        raise ProfileError(f"风格档字段不是颜色: {field}")
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
        raise ProfileError(f"风格档字段不是 #RRGGBB: {field}")
    number = int(text, 16)
    return ((number >> 16) & 255, (number >> 8) & 255, number & 255)


def lookup(data, dotted):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ProfileError(f"风格档缺少字段: {dotted}")
        current = current[part]
    return current


def load_gates(raw):
    gates = dict(DEFAULT_GATES)
    if raw is None:
        return gates
    if not isinstance(raw, dict):
        raise ProfileError("风格档字段 gates 必须是对象")
    number_keys = {
        "border_band": float,
        "border_clear_min": float,
        "accent_distance": float,
        "accent_share_max": float,
    }
    int_keys = {"border_alpha_max": int, "ink_core_min": int}
    for key, caster in number_keys.items():
        if key in raw:
            try:
                gates[key] = caster(raw[key])
            except (TypeError, ValueError) as exc:
                raise ProfileError(f"风格档字段 gates.{key} 不是数字") from exc
    for key in int_keys:
        if key in raw:
            value = raw[key]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ProfileError(f"风格档字段 gates.{key} 不是整数")
            gates[key] = value
    return gates


def load_profile(path: Path):
    if not path.is_file():
        raise ProfileError(f"找不到风格档: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"风格档不是合法 JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ProfileError("风格档必须是 JSON 对象")
    colors = {field: parse_hex(lookup(data, field), field) for field in REQUIRED_COLORS}
    sizes = data.get("sizes")
    if not isinstance(sizes, list) or not sizes:
        raise ProfileError("风格档字段 sizes 必须是非空数组")
    clean_sizes = []
    for size in sizes:
        if isinstance(size, bool) or not isinstance(size, int) or size < 4:
            raise ProfileError("风格档字段 sizes 的每一项必须是大于等于 4 的整数")
        clean_sizes.append(size)
    anchors = data.get("anchors", [])
    if not isinstance(anchors, list) or not all(isinstance(item, str) for item in anchors):
        raise ProfileError("风格档字段 anchors 必须是字符串数组")
    return {
        "colors": colors,
        "sizes": clean_sizes,
        "gates": load_gates(data.get("gates")),
        "anchors": anchors,
    }


def cand_sort_key(path: Path):
    match = re.fullmatch(r"cand-(\d+)", path.stem)
    if match:
        return (0, int(match.group(1)), path.name)
    return (1, 0, path.name)


def anchor_path(profile_path: Path, raw: str, from_profile: bool):
    path = Path(raw).expanduser()
    if from_profile and not path.is_absolute():
        return profile_path.resolve().parent / path
    return path


def collect_anchors(profile_path: Path, profile_anchors, cli_anchors):
    ordered = []
    seen = set()
    pairs = [(raw, True) for raw in profile_anchors] + [(raw, False) for raw in cli_anchors]
    for raw, from_profile in pairs:
        path = anchor_path(profile_path, raw, from_profile)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def has_alpha(image):
    if image.mode in ("RGBA", "LA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def open_image(path: Path):
    from PIL import Image
    from PIL import UnidentifiedImageError

    if not path.is_file():
        raise UnreadableImage(path)
    try:
        with Image.open(path) as image:
            image.load()
            alpha = has_alpha(image)
            size = [image.width, image.height]
            rgba = image.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise UnreadableImage(path) from exc
    return rgba, alpha, size


def color_distance(left, right):
    return math.sqrt(
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    )


def border_is_clear(image, gates):
    width, height = image.size
    band = max(1, int(round(width * gates["border_band"])))
    pixels = image.load()
    total = 0
    clear = 0
    limit = gates["border_alpha_max"]
    for y in range(height):
        for x in range(width):
            if x < band or x >= width - band or y < band or y >= height - band:
                total += 1
                if pixels[x, y][3] <= limit:
                    clear += 1
    if total == 0:
        return False
    return (clear / total) >= gates["border_clear_min"]


def subject_span(image):
    box = image.getbbox()
    if not box:
        return 0.0
    long_side = max(box[2] - box[0], box[3] - box[1])
    canvas = max(image.size)
    if canvas == 0:
        return 0.0
    return long_side / canvas


def accent_share(image, accent, distance):
    pixels = image.load()
    width, height = image.size
    opaque = 0
    near = 0
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 128:
                continue
            opaque += 1
            if color_distance((red, green, blue), accent) <= distance:
                near += 1
    if opaque == 0:
        return 0.0
    return near / opaque


def scale_long_side(image, long_side):
    from PIL import Image

    width, height = image.size
    long_edge = max(width, height)
    if long_edge == 0:
        return image
    if width >= height:
        scaled_w = long_side
        scaled_h = max(1, int(round(height * long_side / width)))
    else:
        scaled_h = long_side
        scaled_w = max(1, int(round(width * long_side / height)))
    if (scaled_w, scaled_h) == (width, height):
        return image
    return image.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)


def largest_component(mask):
    height = len(mask)
    width = len(mask[0]) if height else 0
    seen = bytearray(width * height)
    best = 0
    for y in range(height):
        for x in range(width):
            start = y * width + x
            if not mask[y][x] or seen[start]:
                continue
            stack = [start]
            seen[start] = 1
            count = 0
            while stack:
                current = stack.pop()
                count += 1
                cx = current % width
                cy = current // width
                for ny in range(cy - 1, cy + 2):
                    if ny < 0 or ny >= height:
                        continue
                    for nx in range(cx - 1, cx + 2):
                        if nx < 0 or nx >= width:
                            continue
                        index = ny * width + nx
                        if mask[ny][nx] and not seen[index]:
                            seen[index] = 1
                            stack.append(index)
            if count > best:
                best = count
    return best


def core_sizes(image, accent, distance):
    width, height = image.size
    pixels = image.load()
    ink = [[False] * width for _ in range(height)]
    accent_mask = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 128:
                continue
            if color_distance((red, green, blue), accent) <= distance:
                accent_mask[y][x] = True
            else:
                ink[y][x] = True
    return largest_component(ink), largest_component(accent_mask)


def measure(image, has_alpha_channel, size, accent, gates, min_size):
    share = accent_share(image, accent, gates["accent_distance"])
    clear = border_is_clear(image, gates)
    scaled = scale_long_side(image, min_size)
    ink_core, accent_core = core_sizes(scaled, accent, gates["accent_distance"])
    flags = []
    if not clear:
        flags.append("border-not-clear")
    if share > gates["accent_share_max"]:
        flags.append("accent-too-large")
    if ink_core < gates["ink_core_min"]:
        flags.append(f"ink-core<{gates['ink_core_min']}@{min_size}")
    return {
        "size": size,
        "hasAlpha": has_alpha_channel,
        "borderClear": clear,
        "subjectSpan": round(subject_span(image), 4),
        "accentShare": round(share, 4),
        "inkCore": ink_core,
        "accentCore": accent_core,
        "flags": flags,
    }


def render_chip(source, size, mat, paper):
    from PIL import Image

    chip = Image.new("RGBA", (size, size), mat + (255,))
    inner = size - 2
    if inner <= 0:
        return chip
    paper_rect = Image.new("RGBA", (inner, inner), paper + (255,))
    chip.paste(paper_rect, (1, 1))
    box = source.getbbox()
    if not box:
        return chip
    crop = source.crop(box)
    target = max(1, int(round(0.8 * inner)))
    crop_w, crop_h = crop.size
    if crop_w >= crop_h:
        scaled_w = target
        scaled_h = max(1, int(round(crop_h * target / crop_w)))
    else:
        scaled_h = target
        scaled_w = max(1, int(round(crop_w * target / crop_h)))
    scaled = crop.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
    offset_x = 1 + (inner - scaled_w) // 2
    offset_y = 1 + (inner - scaled_h) // 2
    chip.paste(scaled, (offset_x, offset_y), scaled)
    return chip


def text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def column_origins(count_candidates, count_anchors, column_width):
    origins = []
    cursor = PAGE_MARGIN
    for index in range(count_candidates):
        origins.append(cursor)
        cursor += column_width
        if index != count_candidates - 1:
            cursor += COL_GAP
    if count_candidates and count_anchors:
        cursor += GROUP_GAP
    for index in range(count_anchors):
        origins.append(cursor)
        cursor += column_width
        if index != count_anchors - 1:
            cursor += COL_GAP
    width = cursor + PAGE_MARGIN if origins else PAGE_MARGIN * 2
    return origins, width


def build_sheet(candidates, anchors, sizes, colors):
    from PIL import Image
    from PIL import ImageDraw
    from PIL import ImageFont

    columns = list(candidates) + list(anchors)
    labels = [label for label, _image in columns]
    images = [image for _label, image in columns]
    font = ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    measured = [text_size(probe, label, font) for label in labels]
    column_width = max([max(sizes), *[item[0] for item in measured]])
    label_height = max(item[1] for item in measured)
    origins, width = column_origins(len(candidates), len(anchors), column_width)
    row_height = PAGE_MARGIN + label_height + LABEL_GAP + sum(sizes) + PAGE_MARGIN
    sheet = Image.new("RGB", (width, row_height * 2), colors["palette.page.light"])
    dark = Image.new("RGB", (width, row_height), colors["palette.page.dark"])
    sheet.paste(dark, (0, row_height))
    draw = ImageDraw.Draw(sheet)
    rows = (
        (0, colors["palette.ink"], colors["palette.mat.light"], colors["palette.paper.light"]),
        (
            row_height,
            colors["palette.paper.light"],
            colors["palette.mat.dark"],
            colors["palette.paper.dark"],
        ),
    )
    for top, label_color, mat, paper in rows:
        chips = [render_chip(image, size, mat, paper) for image in images for size in sizes]
        chip_index = 0
        for origin, label in zip(origins, labels):
            label_w, _label_h = text_size(draw, label, font)
            draw.text(
                (origin + (column_width - label_w) // 2, top + PAGE_MARGIN),
                label,
                fill=label_color,
                font=font,
            )
            chip_top = top + PAGE_MARGIN + label_height + LABEL_GAP
            for size in sizes:
                chip = chips[chip_index]
                chip_index += 1
                sheet.paste(chip, (origin + (column_width - size) // 2, chip_top), chip)
                chip_top += size
    return sheet


def missing_profile_message():
    print("错误: 需要 --profile，指向站点的 tile-style.json", file=sys.stderr)
    print("      可以从 examples/tile-style.example.json 复制一份，确认后再用", file=sys.stderr)


class ReviewArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        argv = getattr(self, "review_argv", sys.argv[1:])
        if "--profile" not in argv:
            missing_profile_message()
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv=None):
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    parser = ReviewArgumentParser(
        description="Build a contact sheet and mark file for list-tile candidates."
    )
    parser.review_argv = raw_argv
    parser.add_argument("directory", type=Path, help="Directory that contains cand-*.png")
    parser.add_argument("--profile", type=Path, help="Site style profile JSON")
    parser.add_argument("--anchors", nargs="*", default=[], help="Accepted tiles to show beside candidates")
    args = parser.parse_args(raw_argv)

    if args.profile is None:
        missing_profile_message()
        return 1

    try:
        profile = load_profile(args.profile)
    except ProfileError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if not check_pillow():
        print("错误: 需要安装 Pillow", file=sys.stderr)
        print("      pip install Pillow", file=sys.stderr)
        return 1

    if not args.directory.is_dir():
        print(f"错误: 目录不存在: {args.directory}", file=sys.stderr)
        return 1

    candidates = sorted(args.directory.glob("cand-*.png"), key=cand_sort_key)
    if not candidates:
        print(f"错误: 目录里没有 cand-*.png: {args.directory}", file=sys.stderr)
        return 1

    anchor_paths = collect_anchors(args.profile, profile["anchors"], args.anchors)
    try:
        opened = [open_image(path) for path in candidates]
        anchor_images = [open_image(path)[0] for path in anchor_paths]
    except UnreadableImage as exc:
        print(f"错误: 无法读取图片: {exc}", file=sys.stderr)
        return 2

    gates = profile["gates"]
    min_size = profile["sizes"][-1]
    accent = profile["colors"]["palette.accent"]
    records = []
    candidate_images = []
    for path, (image, alpha, size) in zip(candidates, opened):
        record = measure(image, alpha, size, accent, gates, min_size)
        record["name"] = path.stem
        records.append(record)
        candidate_images.append(image)

    sheet = build_sheet(
        [(path.stem, image) for path, image in zip(candidates, candidate_images)],
        [(f"ref-{index}", image) for index, image in enumerate(anchor_images, start=1)],
        profile["sizes"],
        profile["colors"],
    )
    sheet.save(args.directory / "candidate-review.png")
    review_path = args.directory / "review.json"
    review_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"已写出 {review_path}")
    print(f"已写出 {args.directory / 'candidate-review.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
