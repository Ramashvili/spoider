"""Run the tour's scene without recording, and print the map it leaves behind.

  python3 check_scene.py [--scale 0.15]

The scene is imported from record.py, so this checks the take that will be recorded. Keys
go through a pty instead of tmux and the pauses are scaled down, which makes a two-minute
tour take about twenty seconds. What it proves is the document: every cell where it
belongs, every mark, the fold, the spacing, the shape. It cannot prove the picture.
"""

from __future__ import annotations

import fcntl
import importlib.util
import os
import pty
import struct
import sys
import termios
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP = Path("/tmp/spoider-tour/tour.spoider")
WORKDIR = Path.home() / "Projects/spoider"


def load_scene():
    spec = importlib.util.spec_from_file_location("tour_record", HERE / "record.py")
    if spec is None or spec.loader is None:
        raise ImportError("cannot load record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scene()


def main() -> int:
    scale = 0.15
    argv = sys.argv[1:]
    if "--scale" in argv:
        scale = float(argv[argv.index("--scale") + 1])

    MAP.unlink(missing_ok=True)
    plan = load_scene()
    env = dict(os.environ, TERM="xterm-256color", COLUMNS="150", LINES="50")
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(WORKDIR)
        os.execvpe("uv", ["uv", "run", "spoider", str(MAP)], env)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 150, 0, 0))

    def drain() -> None:
        """The program blocks on its own output if nobody reads it."""
        while True:
            try:
                if not os.read(fd, 65536):
                    return
            except OSError:
                return

    threading.Thread(target=drain, daemon=True).start()
    time.sleep(6)  # the program has to be up before the first key means anything

    started = time.monotonic()
    for pause, payload, _chord in plan:
        time.sleep(pause * scale)
        if payload:
            os.write(fd, payload if isinstance(payload, bytes) else payload.encode())
    print(f"scene sent in {time.monotonic() - started:.1f}s")

    for _ in range(40):
        time.sleep(0.2)
        try:
            if os.waitpid(pid, os.WNOHANG)[0]:
                break
        except ChildProcessError:
            break

    if not MAP.exists():
        print("the scene did not save a map")
        return 1

    import json

    document = json.loads(MAP.read_text())

    def walk(node: dict, depth: int = 0) -> None:
        mark = node.get("mark") or " "
        folded = " (folded)" if node.get("collapsed") else ""
        text = node["text"].replace("\n", " ")
        print("  " * depth + f"[{mark}] {text}{folded}")
        for child in node["children"]:
            walk(child, depth + 1)

    walk(document["root"])
    print(
        f"spacing {document['spacing']} shape {document['layout']} "
        f"colours {document['colours']} cuts {len(document.get('cut_stack') or [])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
