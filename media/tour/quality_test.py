"""Which encoder setting gives sharp text, and what does it cost?

  python3 quality_test.py

Records six seconds of the demo window at each setting, then measures the blend share of a
decoded frame and the bitrate that produced it. Text is what goes soft first, so the
number that matters is the blend share, not the file size on its own.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from sharpen import blend_share

GROUP = "qual" + "probe"
SESSION = "qual"
COLS, ROWS = 150, 50

SETTINGS = [
    ("default (very_high, qp)", []),
    ("ultra (qp)", ["-q", "ultra"]),
    ("cbr 1200 kbps", ["-bm", "cbr", "-q", "1200"]),
    ("cbr 3000 kbps", ["-bm", "cbr", "-q", "3000"]),
]


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def clients() -> list[dict]:
    return json.loads(run(["hyprctl", "clients", "-j"]).stdout or "[]")


def main() -> int:
    run(["tmux", "kill-session", "-t", SESSION])
    process = subprocess.Popen(
        ["kitty", "--instance-group", GROUP, "-o", "window_padding_width=0",
         "-o", "tab_bar_style=hidden", "-o", "tab_bar_min_tabs=2",
         "-T", "qual", "-e", "sh", "-c",
         f'tmux -f /dev/null new-session -d -s {SESSION} "cd {Path.home()}/Projects/spoider && uv run spoider --demo";'
         f" tmux set -g status off; exec tmux attach -t {SESSION}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    window = ""
    try:
        for _ in range(25):
            time.sleep(1)
            window = next((w["address"] for w in clients() if w["pid"] == process.pid), "")
            if window:
                break
        if not window:
            print("no window")
            return 1
        run(["hyprctl", "eval",
             f'hl.dispatch(hl.dsp.window.move({{ workspace = "9", window = "address:{window}" }}))'])
        run(["hyprctl", "eval",
             f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
        run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "9" }))'])
        time.sleep(1.5)
        run(["tmux", "set", "-g", "window-size", "manual"])
        run(["tmux", "resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS)])
        time.sleep(1.0)
        for _ in range(25):
            time.sleep(1)
            if "spoider 0.1.0" in run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout:
                break

        grid = run(["tmux", "display", "-p", "-t", SESSION, "#{client_width}x#{client_height}"]).stdout.strip()
        border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
        client = next(w for w in clients() if w["address"] == window)
        cols, rows = (int(part) for part in grid.split("x"))
        cell_w = (client["size"][0] - 2 * border) / cols
        cell_h = (client["size"][1] - 2 * border) / rows
        width, height = round(COLS * cell_w), round(ROWS * cell_h)
        x, y = client["at"][0] + border, client["at"][1] + border
        print(f"capture {width}x{height}")

        for name, extra in SETTINGS:
            out = Path(f"/tmp/qual-{name.split()[0]}.mp4")
            out.unlink(missing_ok=True)
            recorder = subprocess.Popen(
                ["gpu-screen-recorder", "-w", f"{width}x{height}+{x}+{y}", "-f", "30",
                 "-k", "h264", "-c", "mp4", "-cursor", "no",
                 "-fallback-cpu-encoding", "yes", *extra, "-o", str(out)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(7)
            recorder.send_signal(signal.SIGINT)
            recorder.wait(timeout=60)
            frame = Path(f"/tmp/qual-{name.split()[0]}.png")
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", str(out),
                 "-vframes", "1", str(frame)])
            share, _ = blend_share(frame)
            info = run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=bit_rate:format=duration,size", "-of", "default=noprint_wrappers=1",
                        str(out)]).stdout
            bits = {}
            for line in info.split():
                if "=" in line:
                    key, value = line.split("=", 1)
                    bits[key] = value
            size = int(bits.get("size", 0)) / 1000
            duration = float(bits.get("duration", 1))
            print(f"{name:26} {share:5.2f}% blends | {size/duration*8:7.0f} kbps | "
                  f"{size/duration*8*139/1000:5.1f} MB if the whole take")
    finally:
        run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "1" }))'])
        process.terminate()
        run(["tmux", "kill-session", "-t", SESSION])
    return 0


if __name__ == "__main__":
    sys.exit(main())
