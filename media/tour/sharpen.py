"""How much of the picture is antialiasing? Measures it, does not eyeball it.

  python3 sharpen.py media/spoider.png          # a picture that already exists
  python3 sharpen.py --capture spleen.png       # shoot the demo first, then measure

The terminal's palette is a handful of flat colours, so any pixel that is not within a
short distance of one of the most common colours is a blend: a glyph edge smeared across
two pixels. A bitmap-style face at integer cell metrics should leave very few.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

GROUP = "sharp" + "probe"
SESSION = "sharp"
COLS, ROWS = 150, 50


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def clients() -> list[dict]:
    return json.loads(run(["hyprctl", "clients", "-j"]).stdout or "[]")


def blend_share(path: Path, keep: int = 14, distance: int = 24) -> tuple[float, int]:
    image = Image.open(path).convert("RGB")
    pixels = list(image.getdata())
    common = [colour for colour, _ in Counter(pixels).most_common(keep)]
    blended = 0
    for r, g, b in pixels:
        nearest = min(
            abs(r - cr) + abs(g - cg) + abs(b - cb) for cr, cg, cb in common
        )
        if nearest > distance:
            blended += 1
    return 100 * blended / len(pixels), len(common)


def capture(out: Path, font_family: str | None, adjust: tuple[int, int] | None,
            composition: str | None) -> Path:
    run(["tmux", "kill-session", "-t", SESSION])
    args = [
        "kitty", "--instance-group", GROUP,
        "-o", "window_padding_width=0",
        "-o", "tab_bar_style=hidden", "-o", "tab_bar_min_tabs=2",
    ]
    if font_family:
        args += ["-o", f"font_family={font_family}"]
    if adjust:
        args += ["-o", f"adjust_column_width={adjust[0]}", "-o", f"adjust_line_height={adjust[1]}"]
    if composition:
        args += ["-o", f"text_composition_strategy={composition}"]
    args += ["-T", "sharp", "-e", "sh", "-c",
             f'tmux -f /dev/null new-session -d -s {SESSION} "cd {Path.home()}/Projects/spoider && uv run spoider --demo";'
             f" tmux set -g status off; exec tmux attach -t {SESSION}"]
    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        window = ""
        for _ in range(25):
            time.sleep(1)
            window = next((w["address"] for w in clients() if w["pid"] == process.pid), "")
            if window:
                break
        if not window:
            raise SystemExit("no window")
        run(["hyprctl", "eval",
             f'hl.dispatch(hl.dsp.window.move({{ workspace = "9", window = "address:{window}" }}))'])
        run(["hyprctl", "eval",
             f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
        run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "9" }))'])
        time.sleep(1.5)
        run(["tmux", "set", "-g", "window-size", "manual"])
        run(["tmux", "resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS)])
        time.sleep(1)
        for _ in range(25):
            time.sleep(1)
            if "spoider 0.1.0" in run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout:
                break
        run(["tmux", "send-keys", "-t", SESSION, "-l", "--", "-"])
        time.sleep(1.5)

        grid = run(["tmux", "display", "-p", "-t", SESSION, "#{client_width}x#{client_height}"]).stdout.strip()
        border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
        client = next(w for w in clients() if w["address"] == window)
        cols, rows = (int(part) for part in grid.split("x"))
        cell_w = (client["size"][0] - 2 * border) / cols
        cell_h = (client["size"][1] - 2 * border) / rows
        width, height = round(COLS * cell_w), round(ROWS * cell_h)
        x, y = client["at"][0] + border, client["at"][1] + border
        run(["grim", "-g", f"{x},{y} {width}x{height}", "-t", "png", str(out)])
        print(f"cell {cell_w:.3f}x{cell_h:.3f} -> {width}x{height}")
        return out
    finally:
        run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "1" }))'])
        process.terminate()
        run(["tmux", "kill-session", "-t", SESSION])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("picture", nargs="?")
    parser.add_argument("--capture", dest="shoot")
    parser.add_argument("--font")
    parser.add_argument("--adjust")
    parser.add_argument("--composition")
    args = parser.parse_args()

    if args.shoot:
        adjust = None
        if args.adjust:
            w, h = args.adjust.lower().split("x")
            adjust = (int(w), int(h))
        picture = capture(Path(args.shoot), args.font, adjust, args.composition)
    elif args.picture:
        picture = Path(args.picture)
    else:
        parser.error("give a picture or --capture")

    share, colours = blend_share(picture)
    print(f"{picture}: {share:.2f}% of pixels are blends, across {colours} palette colours")
    return 0


if __name__ == "__main__":
    sys.exit(main())
