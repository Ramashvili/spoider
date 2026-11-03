"""One still of the demo map, for the README.

  python3 shot.py [--workspace 9] [--out ../spoider.png]

Same window, same face and same 150x50 grid as the tour, captured with grim instead of
the recorder: a single frame, no key overlay, no cursor.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
WORKDIR = HOME / "Projects/spoider"
SESSION = "tourshot"
GROUP = "tourshot"
COLS, ROWS = 150, 50


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def hypr(*args: str) -> str:
    return run(["hyprctl", *args]).stdout


def clients() -> list[dict]:
    return json.loads(hypr("clients", "-j") or "[]")


def main() -> int:
    workspace = "9"
    # The published bench. Spleen 8x16 is the terminal's own face and is exact at 1:1,
    # but a video is watched in a window of some other size, so the face is judged on how
    # it survives being scaled. This one does.
    font_family: str | None = "JetBrainsMono Nerd Font"
    font_size: str | None = "12"
    out = Path(__file__).resolve().parent.parent / "spoider.png"
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--workspace":
            workspace = argv[index + 1]
        elif arg == "--font-family":
            font_family = argv[index + 1]
        elif arg == "--font-size":
            font_size = argv[index + 1]
        elif arg == "--out":
            out = Path(argv[index + 1])

    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    subprocess.run(["tmux", "kill-session", "-t", SESSION], capture_output=True)
    time.sleep(0.5)

    font_args = [item for pair in (
        ("-o", f"font_family={font_family}") if font_family else None,
        ("-o", f"font_size={font_size}") if font_size else None,
    ) if pair for item in pair]
    for index, item in enumerate(sys.argv):
        if item == "-o":
            font_args += ["-o", sys.argv[index + 1]]
    kitty = subprocess.Popen(
        [
            "kitty",
            "--instance-group",
            GROUP,
            *font_args,
            "-o",
            "window_padding_width=0",
            "-o",
            "background_opacity=1",
            "-o",
            "dynamic_background_opacity=no",
            "-o",
            "background_blur=0",
            "-o",
            "tab_bar_style=hidden",
            "-o",
            "tab_bar_min_tabs=2",
            "-T",
            "shot",
            "-e",
            "sh",
            "-c",
            f'tmux -f /dev/null new-session -d -s {SESSION} "cd {WORKDIR} && uv run spoider --demo";'
            f" tmux set -g status off; exec tmux attach -t {SESSION}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    window = ""
    for _ in range(30):
        time.sleep(1)
        window = next((w["address"] for w in clients() if w["pid"] == kitty.pid), "")
        if window:
            break
    if not window:
        print("no window appeared")
        return 1

    run(["hyprctl", "eval",
         f'hl.dispatch(hl.dsp.window.move({{ workspace = "{workspace}", window = "address:{window}" }}))'])
    run(["hyprctl", "eval",
         f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
    run(["hyprctl", "eval", f'hl.dispatch(hl.dsp.focus({{ workspace = "{workspace}" }}))'])
    time.sleep(1.5)

    run(["tmux", "set", "-g", "window-size", "manual"])
    run(["tmux", "resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS)])
    time.sleep(1.0)
    for _ in range(30):
        time.sleep(1)
        if "spoider 0.1.0" in run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout:
            break
    # the demo opens at spacing 0; the picture reads better one step tighter
    run(["tmux", "send-keys", "-t", SESSION, "-l", "--", "-"])
    time.sleep(1.0)

    grid = run(["tmux", "display", "-p", "-t", SESSION, "#{client_width}x#{client_height}"]).stdout.strip()
    border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
    client = next(w for w in clients() if w["address"] == window)
    cols, rows = (int(part) for part in grid.split("x"))
    cell_w = (client["size"][0] - 2 * border) / cols
    cell_h = (client["size"][1] - 2 * border) / rows
    x = client["at"][0] + border
    y = client["at"][1] + border
    width = round(COLS * cell_w)
    height = round(ROWS * cell_h)

    shot = run(["grim", "-g", f"{x},{y} {width}x{height}", "-t", "png", str(out)])
    if shot.returncode != 0:
        print("grim failed:", shot.stderr.strip())
        return 1
    print(f"{out} {width}x{height}")

    run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "1" }))'])
    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    run(["tmux", "kill-session", "-t", SESSION])
    return 0


if __name__ == "__main__":
    sys.exit(main())
