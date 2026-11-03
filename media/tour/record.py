"""Record the tour from the real terminal window, and show the keys it used.

  python3 record.py [--workspace 9] [--out media/spoider-tour.mp4] [--no-keys]

The program runs in a kitty window on an empty desktop, inside a tmux window pinned to
150x50, and gpu-screen-recorder captures that pane's pixel box. Nothing is repainted, so
the emoji, the typeface and the colours are the terminal's own: the window is opened
without a font override, so whatever the terminal is configured with is what gets filmed.
A bitmap-style face at integer metrics leaves almost no antialiasing, which is sharp on
screen and smaller after encoding (measured: 0.26% of pixels are blends with Spleen 8x16
against 2.11% with JetBrains Mono).

Key presses are burned in afterwards from the scene itself. A keystroke overlay such as
showmethekey or wshowkeys reads the keyboard devices, and these keys arrive through tmux
send-keys, so an overlay would show nothing at all; the scene already knows every chord it
sends, so it writes them to keys.json and the same times are drawn over the frames.

The scene builds one specific map. Run `check_scene.py` before recording: it plays the
same keys through a pty at reduced speed and prints the map that results, which is how
drift in the anchors is caught without spending a take.
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
SCRATCH = Path(tempfile.gettempdir()) / "spoider-tour"
MAP = SCRATCH / "tour.spoider"
SESSION = "tourrec"
GROUP = "tourrec"
COLS, ROWS = 150, 50

UP, DOWN, LEFT, RIGHT = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C"
ENTER, TAB = "\r", "\t"
ESC = "\x1b"
SHIFT_DOWN = "\x1b[1;2B"


def ctrl(code: int) -> bytes:
    """CSI-u spelling of a ctrl chord: Textual parses it without negotiation."""
    return f"\x1b[{code};5u".encode()


CTRL_A = ctrl(97)
CTRL_D = ctrl(100)
CTRL_I = ctrl(105)
CTRL_J = ctrl(106)
CTRL_K = ctrl(107)
CTRL_L = ctrl(108)
CTRL_S = ctrl(115)
CTRL_U = ctrl(117)
CTRL_X = ctrl(120)
CTRL_Z = ctrl(122)
CTRL_SLASH = ctrl(47)
FAST = 0.017

#: (pause before this chunk, bytes to send, the chord to show over the video)
Step = tuple[float, bytes, str]


def scene() -> list[Step]:
    """(pause, bytes, chord). Every scene starts on the root."""
    plan: list[Step] = []

    def wait(seconds: float) -> None:
        plan.append((seconds, b"", ""))

    def key(seconds: float, payload: bytes, chord: str) -> None:
        plan.append((seconds, payload, chord))

    def say(text: str) -> None:
        wait(0.35)
        for ch in text:
            plan.append((FAST, ch.encode(), ""))
        key(0.25, ENTER.encode(), "⏎")

    def cell(text: str, opens: str, chord: str, *, lead: float = 0.5) -> None:
        key(lead, opens.encode(), chord)
        say(text)
        wait(0.6)

    def up(levels: int) -> None:
        """Climb exactly this many levels.

        LEFT goes to the parent, but on the root it goes into the last child, so the
        number of presses is counted per scene rather than pressed until it stops.
        """
        for index in range(levels):
            key(0.45 if index == 0 else 0.35, LEFT.encode(), "←")
        wait(0.4)

    wait(1.0)

    # three presses to the branch shape, where LEFT always climbs and RIGHT always goes
    # in, so the anchors below are counted instead of guessed. The opening used to dwell
    # on every shape; the tour shows all four of them again later, so it is brisk here
    for index in range(3):
        key(0.45 if index else 0.4, CTRL_L, "^L")
        wait(0.4 if index < 2 else 0.7)

    key(0.5, b"e", "e")
    wait(0.4)
    key(0.1, CTRL_A, "^A")
    wait(0.25)
    say("a mind map")
    wait(0.9)

    cell("why it works", TAB, "⇥")
    cell("one thought in the middle", TAB, "⇥")
    cell("parts arranged around it", ENTER, "⏎")
    cell("each part splits again", ENTER, "⏎")
    wait(0.7)

    up(2)  # from the last child of the first branch to the root
    for pause, after in ((0.9, 1.4), (0.9, 1.6), (0.9, 1.6), (0.9, 1.1)):
        key(pause, CTRL_L, "^L")
        wait(after)

    # second branch, a sibling of the first, with a cell that has children of its own
    key(0.4, RIGHT.encode(), "→")
    cell("what spoider does", ENTER, "⏎")
    cell("the keys you know", TAB, "⇥")
    cell("tab makes a child", TAB, "⇥")
    cell("return makes a sibling", ENTER, "⏎")
    up(2)  # back up to what spoider does
    cell("terminal colours", TAB, "⇥")  # in, not across: these are its children
    cell("plain json", ENTER, "⏎")
    cell("one bar of keys", ENTER, "⏎")
    wait(0.8)

    # -- runs: shift grows one, then the run is deleted and brought back --------------
    up(2)  # from the last child to the root
    key(0.4, RIGHT.encode(), "→")
    key(0.4, DOWN.encode(), "↓")
    key(0.4, RIGHT.encode(), "→")
    key(0.45, SHIFT_DOWN.encode(), "S-↓")
    key(0.4, SHIFT_DOWN.encode(), "S-↓")
    wait(1.8)
    key(0.7, CTRL_D, "^D")
    wait(2.2)
    key(0.8, CTRL_Z, "^Z")
    wait(2.0)
    key(0.5, RIGHT.encode(), "→")  # back into the first child
    key(0.6, CTRL_A, "^A")  # every sibling at once
    wait(1.8)
    key(0.5, ESC.encode(), "esc")
    wait(0.9)

    # -- marks: the palette cycled on one cell, then two more cells lit ---------------
    up(2)  # ^A leaves the cursor on the last cell of the run
    key(0.4, RIGHT.encode(), "→")
    key(0.4, RIGHT.encode(), "→")
    for _ in range(3):
        key(0.45, b"w", "w")
        wait(0.55)
    key(0.12, b"w", "w")
    key(0.12, b"w", "w")
    wait(1.1)
    key(0.45, DOWN.encode(), "↓")
    key(0.4, b"w", "w")
    key(0.4, DOWN.encode(), "↓")
    key(0.4, b"w", "w")
    key(0.4, b"w", "w")
    key(0.4, b"w", "w")
    wait(1.6)

    # -- fold the cell that has children of its own -----------------------------------
    up(2)
    key(0.4, RIGHT.encode(), "→")
    key(0.4, DOWN.encode(), "↓")
    key(0.4, RIGHT.encode(), "→")
    key(0.6, b"t", "t")
    wait(1.6)
    key(0.6, b"t", "t")
    wait(1.0)

    # -- the air between the cells ---------------------------------------------------
    key(0.6, b"=", "=")
    key(0.45, b"=", "=")
    wait(0.8)
    key(0.45, b"=", "=")
    wait(2.0)
    # tighten all the way to the floor, which is -2, then step back up one: the tightest
    # setting is worth seeing once, and a single step of air reads better in a video
    for index in range(6):
        key(0.55 if index == 0 else 0.45, b"-", "-")
    wait(2.2)
    key(0.7, b"=", "=")
    wait(2.6)

    # -- the colouring, both ways ----------------------------------------------------
    key(0.7, b"c", "c")
    wait(2.0)
    key(0.7, b"c", "c")
    wait(1.5)

    # -- one cut, worked on inside the stack -----------------------------------------
    up(2)
    key(0.4, RIGHT.encode(), "→")
    key(0.6, CTRL_K, "^K")
    wait(1.4)
    key(0.7, CTRL_I, "^I")
    wait(1.8)

    key(0.6, b"e", "e")
    wait(0.5)
    key(0.1, CTRL_A, "^A")
    wait(0.25)
    say("a branch that waited on the stack")
    wait(1.3)

    key(0.6, CTRL_J, "^J")
    wait(1.1)
    wait(0.15)
    for ch in "24":
        plan.append((0.18, ch.encode(), ""))
    key(0.35, ENTER.encode(), "⏎")
    wait(2.2)

    # -- out of the panel: the cursor is on what spoider does, so the paste lands there
    key(0.7, CTRL_I, "^I")
    wait(1.3)
    key(0.7, CTRL_U, "^U")
    wait(2.4)

    key(0.4, TAB.encode(), "⇥")
    say("a cell takes as much text as you give it, and the box grows to hold it")
    wait(1.5)
    key(0.7, CTRL_J, "^J")
    wait(1.2)
    for ch in "34":
        plan.append((0.18, ch.encode(), ""))
    key(0.35, ENTER.encode(), "⏎")
    wait(3.2)

    key(0.8, CTRL_L, "^L")
    wait(3.0)

    # -- help, then save and hold ----------------------------------------------------
    key(0.8, CTRL_SLASH, "^/")
    wait(3.4)
    key(0.7, ESC.encode(), "esc")
    wait(1.2)
    key(0.7, CTRL_S, "^S")
    wait(2.4)
    key(0.8, CTRL_X, "^X")
    wait(1.6)
    return plan


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def hypr(*args: str) -> str:
    return run(["hyprctl", *args]).stdout


def tmux(*args: str) -> str:
    return run(["tmux", *args]).stdout


def clients() -> list[dict]:
    return json.loads(hypr("clients", "-j") or "[]")


def workspace_of(name: str) -> None:
    run(["hyprctl", "eval", f'hl.dispatch(hl.dsp.focus({{ workspace = "{name}" }}))'])


def send(payload: bytes | str) -> None:
    """Every byte as hex, so control chords and CSI-u sequences arrive unchanged."""
    data = payload.encode() if isinstance(payload, str) else payload
    run(["tmux", "send-keys", "-t", SESSION, "-H", *[f"{byte:02x}" for byte in data]])


def ass(keys: list[dict], width: int, height: int) -> str:
    """A subtitle file that shows each chord for as long as it is the newest one."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Key,JetBrains Mono,24,&H00E6E6E6,&H000000FF,&H00202020,&H99000000,0,0,0,0,100,100,1,0,3,7,0,1,26,26,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for index, item in enumerate(keys):
        start = item["t"]
        end = keys[index + 1]["t"] if index + 1 < len(keys) else start + 1.0
        end = min(end, start + 1.6)
        if end - start < 0.25:
            end = start + 0.25
        lines.append(f"Dialogue: 0,{stamp(start)},{stamp(end)},Key,,0,0,0,,{item['key']}")
    return head + "\n".join(lines) + "\n"


def stamp(seconds: float) -> str:
    hours, rest = divmod(max(0.0, seconds), 3600)
    minutes, rest = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{rest:05.2f}"


def main() -> int:
    workspace = "9"
    font_family: str | None = None
    font_size: str | None = None
    cbr: str | None = None
    out = WORKDIR / "media" / "spoider-tour.mp4"
    show_keys = True
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--workspace":
            workspace = argv[index + 1]
        elif arg == "--font-family":
            font_family = argv[index + 1]
        elif arg == "--font-size":
            font_size = argv[index + 1]
        elif arg == "--cbr":
            cbr = argv[index + 1]
        elif arg == "--out":
            out = Path(argv[index + 1])
        elif arg == "--no-keys":
            show_keys = False
    raw = out.with_suffix(".raw.mp4")

    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    subprocess.run(["tmux", "kill-session", "-t", SESSION], capture_output=True)
    subprocess.run(["pkill", "-f", "gpu-screen-recorder -w "], capture_output=True)
    time.sleep(0.6)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    MAP.unlink(missing_ok=True)
    raw.unlink(missing_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    font_args = [item for pair in (
        ("-o", f"font_family={font_family}") if font_family else None,
        ("-o", f"font_size={font_size}") if font_size else None,
    ) if pair for item in pair]
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

    run(["hyprctl", "eval",
         f'hl.dispatch(hl.dsp.window.move({{ workspace = "{workspace}", window = "address:{window}" }}))'])
    opaque = run(["hyprctl", "eval",
                  f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
    print(f"opacity: {(opaque.stdout or opaque.stderr).strip() or 'no reply'}")
    workspace_of(workspace)
    time.sleep(1.5)

    tmux("set", "-g", "window-size", "manual")
    tmux("resize-window", "-t", SESSION, "-x", str(COLS), "-y", str(ROWS))
    time.sleep(1.0)

    for _ in range(30):
        time.sleep(1)
        if "spoider 0.1.0" in tmux("capture-pane", "-p", "-t", SESSION):
            break
    time.sleep(1.5)

    pane = tmux("list-panes", "-t", SESSION, "-F", "#{pane_width}x#{pane_height}").strip()
    grid = tmux("display", "-p", "-t", SESSION, "#{client_width}x#{client_height}").strip()
    border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
    client = next(w for w in clients() if w["address"] == window)
    cols, rows = (int(part) for part in grid.split("x"))
    cell_w = (client["size"][0] - 2 * border) / cols
    cell_h = (client["size"][1] - 2 * border) / rows
    x = client["at"][0] + border
    y = client["at"][1] + border
    width = round(COLS * cell_w)
    height = round(ROWS * cell_h)
    print(f"pane {pane} grid {grid} cell {cell_w:.2f}x{cell_h:.2f} -> capture {width}x{height}+{x}+{y}")

    rate_args = ["-bm", "cbr", "-q", cbr] if cbr else []
    recorder = subprocess.Popen(
        ["gpu-screen-recorder", "-w", f"{width}x{height}+{x}+{y}", "-f", "30", "-k", "h264",
         "-c", "mp4", "-cursor", "no", "-encoder", "cpu", "-fallback-cpu-encoding", "yes",
         *rate_args,
         "-o", str(raw)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.2)
    started = time.monotonic()
    keys: list[dict] = []

    for pause, payload, chord in scene():
        time.sleep(pause)
        if payload:
            send(payload)
        if chord:
            keys.append({"t": round(time.monotonic() - started, 3), "key": chord})
    print(f"scene finished after {time.monotonic() - started:.1f}s")

    time.sleep(1.0)
    recorder.send_signal(2)
    try:
        recorder.wait(timeout=30)
    except subprocess.TimeoutExpired:
        recorder.kill()

    workspace_of("1")
    subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
    tmux("kill-session", "-t", SESSION)

    if keys and show_keys:
        manifest = SCRATCH / "keys.json"
        manifest.write_text(json.dumps(keys, indent=0) + "\n")
        subtitle = SCRATCH / "keys.ass"
        subtitle.write_text(ass(keys, width, height))
        burn = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf", f"ass={subtitle}",
             "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(out)],
            capture_output=True, text=True,
        )
        if burn.returncode != 0:
            print("the key overlay failed, keeping the plain recording")
            print(burn.stderr[-400:])
            raw.replace(out)
        else:
            raw.unlink(missing_ok=True)
            print(f"{len(keys)} chords drawn in over the frames")
    else:
        raw.replace(out)

    probe = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,nb_frames", "-show_entries", "format=duration,size",
                 "-of", "default=noprint_wrappers=1", str(out)]).stdout
    print(probe.strip())
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
