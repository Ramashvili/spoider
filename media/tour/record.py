"""Record the tour from the real terminal window.

  python3 record.py [--workspace 9] [--font 12] [--out media/spoider-tour.mp4]

The program runs in a kitty window on an empty desktop, inside a tmux window pinned to
150x50, and gpu-screen-recorder captures that pane's pixel box. Nothing is repainted
afterwards: the emoji, the typeface and the colours are the terminal's own. Keys are
still scripted, sent through tmux as hex so every byte arrives exactly as written.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
WORKDIR = HOME / "Projects/spoider"
MAP = "/tmp/spoider-tour/tour.spoider"
SESSION = "tourrec"
GROUP = "tourrec"
COLS, ROWS = 150, 50

UP, DOWN, LEFT, RIGHT = b"\x1b[A", b"\x1b[B", b"\x1b[D", b"\x1b[C"
ENTER, TAB = b"\r", b"\t"
ESC = b"\x1b"
SHIFT_DOWN = b"\x1b[1;2B"


def ctrl(code: int) -> bytes:
    """CSI-u spelling of a ctrl chord: Textual parses it without negotiation."""
    return f"\x1b[{code};5u".encode()


CTRL_A = ctrl(97)
CTRL_I = ctrl(105)
CTRL_J = ctrl(106)
CTRL_K = ctrl(107)
CTRL_L = ctrl(108)
CTRL_S = ctrl(115)
CTRL_U = ctrl(117)
CTRL_X = ctrl(120)
CTRL_SLASH = ctrl(47)
FAST = 0.017


def scene() -> list[tuple[float, bytes]]:
    """(pause before this chunk, bytes). Every scene starts on the root."""
    plan: list[tuple[float, bytes]] = []

    def wait(seconds: float) -> None:
        plan.append((seconds, b""))

    def key(seconds: float, *keys: bytes) -> None:
        for k in keys:
            plan.append((seconds, k))

    def say(text: str) -> None:
        wait(0.35)
        for ch in text:
            plan.append((FAST, ch.encode()))
        key(0.25, ENTER)

    def cell(text: str, opens: bytes = ENTER, *, lead: float = 0.5) -> None:
        key(lead, opens)
        say(text)
        wait(0.6)

    def up(levels: int) -> None:
        for index in range(levels):
            key(0.45 if index == 0 else 0.35, LEFT)
        wait(0.4)

    wait(1.6)
    key(0.8, CTRL_L)
    key(1.1, CTRL_L)
    key(1.1, CTRL_L)
    wait(1.2)

    key(0.5, b"e")
    wait(0.4)
    key(0.1, CTRL_A)
    wait(0.25)
    say("a mind map")
    wait(0.9)

    cell("why it works", TAB)
    cell("one thought in the middle", TAB)
    cell("parts arranged around it", ENTER)
    cell("each part splits again", ENTER)
    wait(0.7)

    up(2)
    key(0.9, CTRL_L)
    wait(1.4)
    key(0.9, CTRL_L)
    wait(1.6)
    key(0.9, CTRL_L)
    wait(1.6)
    key(0.9, CTRL_L)
    wait(1.1)

    key(0.4, RIGHT)
    cell("what spoider does", ENTER)
    cell("nano chords", TAB)
    cell("terminal colours", ENTER)
    cell("plain json", ENTER)
    cell("one bar of keys", ENTER)
    wait(0.8)

    up(2)
    key(0.4, RIGHT)
    key(0.4, DOWN)
    key(0.4, RIGHT)
    key(0.45, SHIFT_DOWN)
    key(0.4, SHIFT_DOWN)
    wait(1.8)
    key(0.6, CTRL_A)
    wait(1.8)
    key(0.5, ESC)
    wait(0.9)

    up(2)
    key(0.4, RIGHT)
    key(0.4, RIGHT)
    for _ in range(3):
        key(0.45, b"m")
        wait(0.55)
    key(0.12, b"m", b"m")
    wait(1.1)
    key(0.45, DOWN)
    key(0.4, b"m")
    key(0.4, DOWN)
    key(0.4, b"m", b"m", b"m")
    wait(1.6)

    up(2)
    key(0.4, RIGHT)
    key(0.6, b"t")
    wait(1.5)
    key(0.6, b"t")
    wait(1.0)

    key(0.6, b"=")
    key(0.45, b"=")
    wait(0.8)
    key(0.45, b"=")
    wait(2.0)
    key(0.55, b"-")
    key(0.45, b"-")
    wait(0.8)
    key(0.45, b"-")
    wait(1.6)

    key(0.7, b"c")
    wait(2.0)
    key(0.7, b"c")
    wait(1.5)

    key(0.6, CTRL_K)
    wait(1.4)
    key(0.7, CTRL_I)
    wait(1.8)

    key(0.6, b"e")
    wait(0.5)
    key(0.1, CTRL_A)
    wait(0.25)
    say("a branch that waited on the stack")
    wait(1.3)

    key(0.6, CTRL_J)
    wait(1.1)
    wait(0.15)
    for ch in "24":
        plan.append((0.18, ch.encode()))
    key(0.35, ENTER)
    wait(2.2)

    key(0.7, CTRL_I)
    wait(1.3)
    key(0.7, CTRL_U)
    wait(2.4)

    key(0.4, RIGHT)
    cell("a cell takes as much text as you give it, and the box grows to hold it", ENTER)
    wait(1.5)
    key(0.7, CTRL_J)
    wait(1.2)
    for ch in "34":
        plan.append((0.18, ch.encode()))
    key(0.35, ENTER)
    wait(3.2)

    key(0.8, CTRL_L)
    wait(3.0)

    key(0.8, CTRL_SLASH)
    wait(3.4)
    key(0.7, ESC)
    wait(1.2)
    key(0.7, CTRL_S)
    wait(2.4)
    key(0.8, CTRL_X)
    wait(1.6)
    return plan


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def hypr(*args: str) -> str:
    return run(["hyprctl", *args]).stdout


def tmux(*args: str) -> str:
    return run(["tmux", *args]).stdout


def clients() -> list[dict]:
    return json.loads(hypr("clients", "-j") or "[]")


def workspace_of(name: str) -> None:
    run(["hyprctl", "eval", f'hl.dispatch(hl.dsp.focus({{ workspace = "{name}" }}))'])


def send(payload: bytes) -> None:
    """Every byte as hex, so control chords and CSI-u sequences arrive unchanged."""
    words = [f"{byte:02x}" for byte in payload]
    run(["tmux", "send-keys", "-t", SESSION, "-H", *words])


def main() -> int:
    workspace = "9"
    font = "12"
    out = WORKDIR / "media" / "spoider-tour.mp4"
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--workspace":
            workspace = argv[index + 1]
        elif arg == "--font":
            font = argv[index + 1]
        elif arg == "--out":
            out = Path(argv[index + 1])

    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    subprocess.run(["tmux", "kill-session", "-t", SESSION], capture_output=True)
    subprocess.run(["pkill", "-f", "gpu-screen-recorder -w "], capture_output=True)
    time.sleep(0.6)
    Path(MAP).unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    kitty = subprocess.Popen(
        [
            "kitty",
            "--instance-group",
            GROUP,
            "-o",
            "font_family=JetBrainsMono Nerd Font",
            "-o",
            f"font_size={font}",
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
            "tour",
            "-e",
            "sh",
            "-c",
            f'tmux -f /dev/null new-session -d -s {SESSION} "cd {WORKDIR} && uv run spoider {MAP}";'
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

    run(["hyprctl", "eval", f'hl.dispatch(hl.dsp.window.move({{ workspace = "{workspace}", window = "address:{window}" }}))'])
    opaque = run(["hyprctl", "eval",
                  f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
    print(f"opacity: {(opaque.stdout or opaque.stderr).strip() or 'no reply'}")
    workspace_of(workspace)
    time.sleep(1.5)

    tmux("set", "-g", "window-size", "manual")
    tmux("resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS))
    time.sleep(1.0)

    # wait for the program's first frame rather than for a fixed number of seconds
    for _ in range(30):
        time.sleep(1)
        screen = tmux("capture-pane", "-p", "-t", SESSION)
        if "spoider 0.1.0" in screen:
            break
    time.sleep(1.5)

    pane = tmux("list-panes", "-t", SESSION, "-F", "#{pane_width}x#{pane_height}").strip()
    grid = tmux("display", "-p", "-t", SESSION, "#{client_width}x#{client_height}").strip()
    border = int((run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0]))
    client = next(w for w in clients() if w["address"] == window)
    cols, rows = (int(part) for part in grid.split("x"))
    cell_w = (client["size"][0] - 2 * border) / cols
    cell_h = (client["size"][1] - 2 * border) / rows
    x = client["at"][0] + border
    y = client["at"][1] + border
    width = round(COLS * cell_w)
    height = round(ROWS * cell_h)
    print(f"pane {pane} grid {grid} cell {cell_w:.2f}x{cell_h:.2f} -> capture {width}x{height}+{x}+{y}")

    recorder = subprocess.Popen(
        [
            "gpu-screen-recorder",
            "-w",
            f"{width}x{height}+{x}+{y}",
            "-f",
            "30",
            "-k",
            "h264",
            "-c",
            "mp4",
            "-cursor",
            "no",
            "-fallback-cpu-encoding",
            "yes",
            "-o",
            str(out),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.2)

    started = time.monotonic()
    for pause, payload in scene():
        time.sleep(pause)
        if payload:
            send(payload)
    print(f"scene finished after {time.monotonic() - started:.1f}s")

    time.sleep(1.0)
    recorder.send_signal(signal.SIGINT)
    try:
        recorder.wait(timeout=30)
    except subprocess.TimeoutExpired:
        recorder.kill()

    workspace_of("1")
    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    tmux("kill-session", "-t", SESSION)

    probe = run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,nb_frames", "-show_entries", "format=duration,size",
         "-of", "default=noprint_wrappers=1", str(out)]
    ).stdout
    print(probe.strip())
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
