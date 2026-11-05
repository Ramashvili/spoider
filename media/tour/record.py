"""Record the tour from the real terminal window, and show the keys it used.

  python3 record.py [--workspace 9] [--out media/spoider-tour.mp4] [--no-keys]

This is a personal bench, not part of the program. It is tuned to this machine (Hyprland,
kitty, tmux, wf-recorder) and its paths assume the author's home directory, so treat it as
a record of how the tour was made rather than as something to install or support. It stays
in the repository so the tour can be remade rather than reverse-engineered.

The program runs in a kitty window on an empty desktop, inside a tmux window pinned to
150x50, and wf-recorder captures that pane's pixel box losslessly. Nothing is repainted, so
the emoji, the typeface and the colours are the terminal's own.

The face is JetBrains Mono at 12, which is what the published tour was filmed in. A face is
judged on how it survives being scaled, because a video is watched in a window of some
other size, and that is the trade this one wins.

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
#: Every take keeps its lossless master here, so a candidate can be looked at again and
#: re-encoded without re-filming. Nothing here is published.
TAKES = HOME / "Videos" / "spoider"
MAP = SCRATCH / "tour.spoider"
SESSION = "tourrec"
GROUP = "tourrec"
#: The pane the tour is filmed in, in cells. A 150x50 pane at this face is taller than
#: 1080 lines, so the window cannot hold it; 138x46 is the same face at a size the screen
#: has room for, and the pane fills the window exactly.
COLS, ROWS = 138, 46

UP, DOWN, LEFT, RIGHT = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C"
ENTER, TAB = "\r", "\t"
ESC = "\x1b"
SHIFT_DOWN = "\x1b[1;2B"
ALT_UP, ALT_DOWN = "\x1b[1;3A", "\x1b[1;3B"
HOME_KEY = "\x1b[1~"  # xterm spelling: `\x1b[H` is split as esc + `[H` by some parsers


def ctrl(code: int) -> bytes:
    """CSI-u spelling of a ctrl chord: Textual parses it without negotiation."""
    return f"\x1b[{code};5u".encode()


CTRL_A = ctrl(97)
CTRL_D = ctrl(100)
CTRL_J = ctrl(106)
CTRL_K = ctrl(107)
CTRL_L = ctrl(108)
CTRL_S = ctrl(115)
CTRL_U = ctrl(117)
CTRL_X = ctrl(120)
CTRL_Z = ctrl(122)
CTRL_F = ctrl(102)
CTRL_SLASH = ctrl(47)
FAST = 0.017

#: (pause before this chunk, bytes to send, the chord to show over the video)
Step = tuple[float, bytes, str]


#: The long note, taken whole from the README's "Moving branches with the stack" and
#: stripped of its backticks. One line, so `^J` is what makes it a paragraph.
LONG = (
    "Cutting with ^K places a branch onto a stack, and ^U pastes the most recent cut "
    "under whichever cell you select next. If you are reorganising a large map, press p "
    "to open the stack side-by-side: you can browse what you cut, edit or fold items "
    "inside it, or reorder them before pasting them back."
)


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
        """Climb exactly this many levels; in the branch shape LEFT is always the parent.

        Half a second a press: at 0.3 s the program is still redrawing and an arrow is
        dropped, which moves every anchor after it by one cell without saying so.
        """
        for _ in range(levels):
            key(0.5, LEFT.encode(), "←")
        wait(0.4)

    def root() -> None:
        """The main cell of the tree, whatever shape the map is drawn in."""
        key(0.35, HOME_KEY.encode(), "Home")
        wait(0.35)

    def sibling(steps: int) -> None:
        for _ in range(steps):
            key(0.5, DOWN.encode(), "↓")

    wait(0.6)  # the first seconds are brisk: the map is worth more than a held title

    # Three presses to the branch shape, measured: LEFT always climbs there and RIGHT
    # always goes in, so every anchor below is a climb or a sibling, never a guess.
    for index in range(3):
        key(0.45, CTRL_L, "^L")
        wait(0.35 if index < 2 else 0.6)

    # The root's name, typed the way a name is typed.
    key(0.45, b"e", "e")
    wait(0.35)
    key(0.1, CTRL_A, "^A")
    wait(0.25)
    say("spoider")
    wait(0.8)

    # -- four levels deep, in the manual's own words -----------------------------------
    cell("a mind map in a terminal", TAB, "⇥")
    cell("the map is a JSON file", TAB, "⇥")
    cell("read it", TAB, "⇥")
    cell("diff it", TAB, "⇥")
    cell("keep it in git", ENTER, "⏎")
    wait(0.7)

    # -- marks on the two cells at the bottom, straight after they are made ------------
    for _ in range(3):
        key(0.5, b"w", "w")
        wait(0.55)
    wait(0.9)
    key(0.5, UP.encode(), "↑")
    key(0.5, b"w", "w")
    wait(1.2)

    # -- fold the branch that has children, then open it again -------------------------
    for _ in range(2):
        key(0.5, LEFT.encode(), "←")  # diff it > read it > the map is a JSON file
    wait(0.4)
    key(0.6, b"t", "t")
    wait(1.6)
    key(0.6, b"t", "t")
    wait(0.9)

    # -- the second branch, and the third ---------------------------------------------
    key(0.5, LEFT.encode(), "←")  # back to a mind map in a terminal
    wait(0.4)
    cell("every colour is your terminal's", TAB, "⇥")  # a child of it, not a new branch
    key(0.5, LEFT.encode(), "←")
    wait(0.4)
    cell("making cells", ENTER, "⏎")
    wait(0.5)

    # -- reordering, where the branch stands ------------------------------------------
    key(0.55, ALT_UP.encode(), "M-↑")
    wait(1.1)
    key(0.55, ALT_DOWN.encode(), "M-↓")
    wait(1.0)
    key(0.55, ALT_UP.encode(), "M-↑")
    wait(1.5)

    cell("tab makes a child", TAB, "⇥")
    cell("return makes a sibling", ENTER, "⏎")
    cell("shift+return starts a line", TAB, "⇥")
    for _ in range(2):
        key(0.5, LEFT.encode(), "←")  # shift+return > return makes a sibling > making cells
    wait(0.4)

    cell("the cut stack", ENTER, "⏎")
    cell("^K cuts a branch onto the stack", TAB, "⇥")
    cell("^U pastes the newest cut", TAB, "⇥")

    # -- the long note: typed whole, justified, folded on the stack, pasted back -------
    for _ in range(2):
        key(0.5, LEFT.encode(), "←")  # up to the cut stack
    wait(0.4)
    key(0.5, TAB.encode(), "⇥")
    say(LONG)
    wait(1.0)
    key(0.7, CTRL_J, "^J")
    wait(1.1)
    for ch in "34":
        plan.append((0.18, ch.encode(), ""))
    key(0.35, ENTER.encode(), "⏎")
    wait(3.2)

    key(0.7, CTRL_K, "^K")
    wait(1.4)
    key(0.7, b"p", "p")
    wait(2.0)
    key(0.6, b"t", "t")
    wait(1.4)
    key(0.6, b"t", "t")
    wait(1.0)
    key(0.7, b"p", "p")
    wait(1.2)
    root()
    key(0.7, CTRL_U, "^U")
    wait(3.0)

    # -- the four shapes, late, so a dropped press cannot move an anchor ---------------
    root()
    for pause, after in ((0.8, 1.3), (0.8, 1.4), (0.8, 1.4), (0.8, 1.2)):
        key(pause, CTRL_L, "^L")
        wait(after)

    # -- the air between the cells: -1 down to -4 slowly, then back to -1 quickly ------
    key(0.55, b"-", "-")
    wait(1.2)
    key(0.55, b"-", "-")
    wait(1.0)
    key(0.55, b"-", "-")
    wait(1.0)
    key(0.65, b"-", "-")
    wait(3.4)  # -4: four steps tighter than the default, where the gaps are narrowest
    for _ in range(3):
        key(0.22, b"=", "=")
    wait(1.8)

    # -- the colouring, both ways ------------------------------------------------------
    key(0.7, b"c", "c")
    wait(2.4)
    key(0.7, b"c", "c")
    wait(1.2)

    # -- help, then save and hold ------------------------------------------------------
    key(0.8, b"?", "?")
    wait(3.4)
    key(0.7, ESC.encode(), "esc")
    wait(1.0)
    key(0.7, CTRL_S, "^S")
    wait(2.0)
    # No quit key: the recorder is stopped while the map is still on screen, because a
    # window that closes lets the desktop into the last seconds of the take. The harness
    # kills the program after the recorder has stopped.
    wait(0.8)
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


def short_scene() -> list[Step]:
    """Ten seconds of the work a tour shows: walking the map, typing, relayout."""
    plan: list[Step] = [(1.5, b"", "")]
    for _ in range(5):
        plan.append((0.18, b"\x0e", "^N"))
    plan.append((0.3, b"\x10", "^P"))
    plan.append((0.6, b"\t", "tab"))
    plan.append((0.35, b"", ""))
    for character in "sharp letters hold their shape":
        plan.append((FAST, character.encode(), ""))
    plan.append((0.25, ENTER.encode(), "⏎"))
    plan.append((0.8, b"-", "-"))
    plan.append((0.5, b"-", "-"))
    plan.append((0.9, b"\x0c", "^L"))
    plan.append((1.2, b"", ""))
    return plan


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
    # The published bench. Spleen 8x16 is the terminal's own face and is exact at 1:1,
    # but a video is watched in a window of some other size, so the face is judged on how
    # it survives being scaled. This one does.
    font_family: str | None = "JetBrainsMono Nerd Font"
    font_size: str | None = "12"
    cbr: str | None = None
    lossless = False
    capture = "wf"  # the default: a lossless master, encoded once for publishing
    short = False
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
        elif arg == "--lossless":
            lossless = True
        elif arg == "--capture":
            capture = argv[index + 1]
        elif arg == "--out":
            out = Path(argv[index + 1])
        elif arg == "--no-keys":
            show_keys = False
        elif arg == "--short":
            short = True
            show_keys = False
    TAKES.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    if capture == "wf":
        raw = TAKES / f"{out.stem}-{stamp}.master.mkv"
    else:
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
            f"initial_window_width={COLS}c",
            "-o",
            f"initial_window_height={ROWS}c",
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
        if "spoider 0." in tmux("capture-pane", "-p", "-t", SESSION):
            break
    time.sleep(1.5)

    pane = tmux("list-panes", "-t", SESSION, "-F", "#{pane_width}x#{pane_height}").strip()
    if pane != f"{COLS}x{ROWS}":
        print(f"the pane is {pane}, not {COLS}x{ROWS}: the window would not hold the scene")
        subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
        return 1
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
    screen = hypr("monitors", "-j")
    monitor = json.loads(screen or "[]")[0]
    room_x, room_y = monitor["width"] - x, monitor["height"] - y
    print(f"pane {pane} grid {grid} cell {cell_w:.2f}x{cell_h:.2f} -> capture {width}x{height}+{x}+{y}")
    print(f"screen {monitor['width']}x{monitor['height']} leaves {room_x}x{room_y}")
    if width > room_x or height > room_y:
        # wf-recorder falls back to the whole output when the region does not fit, and a
        # tour that quietly films the desktop is worse than no tour at all
        print("the pane does not fit on this screen: film it in a smaller face, or fewer rows")
        subprocess.run(["pkill", "-f", f"instance-group {GROUP}"], capture_output=True)
        tmux("kill-session", "-t", SESSION)
        return 1

    rate_args = ["-bm", "cbr", "-q", cbr] if cbr else []
    if lossless:
        # what the screen shows, in the file: constant QP at 0 is lossless in x264
        rate_args = ["-bm", "qp", "-q", "0"]
    if capture == "wf":
        # wf-recorder grabs the same wlroots region and, with libx264rgb at crf 0, keeps
        # every pixel exactly as composited. The master is never published: it is the
        # input to the one encode that is.
        recorder = subprocess.Popen(
            ["wf-recorder", "-g", f"{x},{y} {width}x{height}", "-r", "30", "-f", str(raw),
             "-D", "-c", "libx264rgb", "-p", "crf=0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
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

    for pause, payload, chord in (short_scene() if short else scene()):
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

    # One encode, from the master to the file that ships. With wf-recorder the master is
    # lossless, so this is the only place the picture is compressed, and the keys are
    # drawn here rather than over an already compressed recording.
    if capture == "wf" or (keys and show_keys):
        encode = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw)]
        if keys and show_keys:
            manifest = SCRATCH / "keys.json"
            manifest.write_text(json.dumps(keys, indent=0) + "\n")
            subtitle = SCRATCH / "keys.ass"
            subtitle.write_text(ass(keys, width, height))
            encode += ["-vf", f"ass={subtitle}"]
        encode += ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", str(out)]
        burn = subprocess.run(encode, capture_output=True, text=True)
        if burn.returncode != 0:
            print("the encode failed, keeping the master as it is")
            print(burn.stderr[-400:])
            if raw.exists():
                raw.replace(out)
        else:
            print(f"{len(keys)} chords drawn in over the frames")
            # the master is kept: it is what a later encode, a different bitrate or a
            # different overlay is made from, and it is never published
            print(f"master kept at {raw} ({raw.stat().st_size / 1_000_000:.0f} MB)")
    else:
        raw.replace(out)

    probe = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height,nb_frames", "-show_entries", "format=duration,size",
                 "-of", "default=noprint_wrappers=1", str(out)]).stdout
    print(probe.strip())
    info = dict(
        line.split("=", 1) for line in probe.strip().splitlines() if "=" in line
    )
    filmed = (int(info.get("width", 0)), int(info.get("height", 0)))
    # yuv420p needs even sides, so one pixel of rounding is the encoder's, not the pane's
    if any(abs(a - b) > 1 for a, b in zip(filmed, (width, height))):
        print(f"filmed {filmed[0]}x{filmed[1]}, wanted {width}x{height}: "
              "the take has something in it other than the pane")
        return 1
    print(f"written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
