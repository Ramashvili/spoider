"""Is the recording faithful to the screen? Six seconds per setting, measured.

A personal bench like record.py: it measures how far a file is from this screen.

  python3 fidelity.py [--font-family ...] [--font-size ...]

For each encoder setting: take a still of the window with grim, record six seconds of the
same static screen, decode one frame, and compare it with the still. A faithful recorder
gives a worst-channel difference of 0. Everything else is the encoder, numbered.

Short on purpose. The question is about the encoder, not about the tour, and six seconds
answers it as well as two minutes at a hundredth of the cost.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops

GROUP = "fid" + "elity"
SESSION = "fid"
COLS, ROWS = 150, 50

#: (name, gpu-screen-recorder extra args, wf-recorder codec args)
SETTINGS = [
    ("master (libx264rgb crf 0)", [], ["-c", "libx264rgb", "-p", "crf=0"]),
]


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def clients() -> list[dict]:
    return json.loads(run(["hyprctl", "clients", "-j"]).stdout or "[]")


def compare(a: Path, b: Path) -> tuple[int, int, str]:
    """(worst channel difference, pixels that differ, distribution of the change)."""
    first, second = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    width = min(first.size[0], second.size[0])
    height = min(first.size[1], second.size[1])
    first = first.crop((0, 0, width, height))
    second = second.crop((0, 0, width, height))
    difference = ImageChops.difference(first, second)
    values = [max(pixel) for pixel in difference.getdata()]
    total = len(values) or 1
    worst = max(values)
    differing = sum(1 for value in values if value)
    mean = sum(values) / total
    tails = " ".join(f"over {limit}: {100 * sum(1 for v in values if v > limit) / total:4.1f}%"
                     for limit in (8, 32, 64, 128))
    return worst, differing, f"mean {mean:4.1f} | {tails}"


def main() -> int:
    font_args: list[str] = []
    for flag in ("--font-family", "--font-size"):
        if flag in sys.argv:
            font_args += ["-o", f"{flag[2:].replace('-', '_')}={sys.argv[sys.argv.index(flag) + 1]}"]

    run(["tmux", "kill-session", "-t", SESSION])
    process = subprocess.Popen(
        ["kitty", "--instance-group", GROUP, *font_args, "-o", "window_padding_width=0",
         "-o", "tab_bar_style=hidden", "-o", "tab_bar_min_tabs=2", "-T", "fidelity",
         "-e", "sh", "-c",
         f'tmux -f /dev/null new-session -d -s {SESSION} "cd {Path.home()}/Projects/spoider && uv run spoider --demo";'
         f" tmux set -g status off; exec tmux attach -t {SESSION}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    window = ""
    try:
        for _ in range(30):
            time.sleep(1)
            window = next((w["address"] for w in clients() if w["pid"] == process.pid and w["mapped"]), "")
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
        time.sleep(2)
        run(["tmux", "set", "-g", "window-size", "manual"])
        run(["tmux", "resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS)])
        time.sleep(1)
        for _ in range(25):
            time.sleep(1)
            if "spoider 0.1.0" in run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout:
                break
        time.sleep(2)

        grid = run(["tmux", "display", "-p", "-t", SESSION, "#{client_width}x#{client_height}"]).stdout.strip()
        border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
        client = next(w for w in clients() if w["address"] == window)
        cols, rows = (int(part) for part in grid.split("x"))
        cell_w = (client["size"][0] - 2 * border) / cols
        cell_h = (client["size"][1] - 2 * border) / rows
        width, height = round(COLS * cell_w), round(ROWS * cell_h)
        x, y = client["at"][0] + border, client["at"][1] + border
        if "--dx" in sys.argv:
            x += int(sys.argv[sys.argv.index("--dx") + 1])
        if "--dy" in sys.argv:
            y += int(sys.argv[sys.argv.index("--dy") + 1])
        print(f"cell {cell_w:.3f}x{cell_h:.3f} -> capture {width}x{height}")

        for name, extra, wf in SETTINGS:
            still = Path(f"/tmp/fid-{name.split()[0]}-still.png")
            video = Path(f"/tmp/fid-{name.split()[0]}.mp4")
            frame = Path(f"/tmp/fid-{name.split()[0]}-frame.png")
            video.unlink(missing_ok=True)
            run(["grim", "-g", f"{x},{y} {width}x{height}", "-t", "png", str(still)])
            if wf is not None:
                command = ["wf-recorder", "-g", f"{x},{y} {width}x{height}", "-r", "30",
                           "-D", "-f", str(video.with_suffix(".mkv")), *wf]
                video = video.with_suffix(".mkv")
            else:
                video = video.with_suffix(".mp4")
                command = ["gpu-screen-recorder", "-w", f"{width}x{height}+{x}+{y}", "-f", "30",
                           "-k", "h264", "-c", "mp4", "-cursor", "no", "-encoder", "cpu",
                           "-fallback-cpu-encoding", "yes", *extra, "-o", str(video)]
            recorder = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(4)
            # Movement, so the take has something to encode. The frame compared below is
            # taken at two seconds, before any of this, so the still still matches it.
            # 2d is "-", 3d is "=": spacing, which redraws the whole map
            before = run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout
            run(["tmux", "send-keys", "-H", "-t", SESSION, "2d", "2d", "2d", "3d", "3d"])
            time.sleep(0.5)
            after = run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout
            spacing = next((line for line in after.splitlines() if "spacing" in line), "")
            print(f"  motion: {'seen' if before != after else 'NOT SEEN'}  {spacing[-58:].strip()}")
            time.sleep(3)
            recorder.send_signal(signal.SIGINT)
            recorder.wait(timeout=60)
            if not video.exists() or video.stat().st_size < 1000:
                print(f"{name:26} unavailable")
                continue
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", str(video),
                 "-vframes", "1", str(frame)])
            worst, differing, _ = compare(still, frame)
            size_kb = video.stat().st_size / 1000
            duration = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=noprint_wrappers=1:nokey=1", str(video)]).stdout.strip() or 1)
            print(f"{name:26} master on disk {size_kb / 1000:5.1f} MB for {duration:4.1f} s "
                  f"= {size_kb / 1000 / duration:5.3f} MB/s")
            print(f"{name:26} worst difference {worst:3} | {differing:7} pixels differ | "
                  f"{size_kb / duration * 139 / 1000:5.1f} MB if it ran 139 s")

            if wf is not None:
                # the published file, made the way record.py makes it
                published = Path(f"/tmp/fid-{name.split()[0]}-published.mp4")
                published_frame = Path(f"/tmp/fid-{name.split()[0]}-published.png")
                encode = run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                              "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                              "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(published)])
                if encode.returncode == 0:
                    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", str(published),
                         "-vframes", "1", str(published_frame)])
                    worst, differing, spread = compare(still, published_frame)
                    published_kb = published.stat().st_size / 1000
                    print(f"{'published (crf 20)':26} worst difference {worst:3} | "
                          f"{differing:7} pixels differ | "
                          f"{published_kb / duration * 139 / 1000:5.1f} MB for the take")
                    print(f"{'':26} {spread}")
    finally:
        run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "1" }))'])
        process.terminate()
        run(["tmux", "kill-session", "-t", SESSION])
    return 0


if __name__ == "__main__":
    sys.exit(main())
