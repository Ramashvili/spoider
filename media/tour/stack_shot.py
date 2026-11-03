"""A still of the stack panel, for the README section that explains it.

  python3 stack_shot.py [--out ../spoider-stack.png]

Same real window as shot.py, but the pane is the whole window instead of 150x50, the face is
the small Spleen, and the map is a taxonomy large enough to run off every edge. Five
branches are already on the cut stack, two of them with children, so the panel shows both
shapes of entry.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
WORKDIR = HOME / "Projects/spoider"
SCRATCH = Path("/tmp/spoider-stackshot")
SESSION = "stackshot"
GROUP = "stackshot"

#: The map is written to disk rather than typed, because the picture needs a document that
#: is already big: a taxonomy five levels deep, clipped by the screen on all four sides.
TAXONOMY: dict[str, object] = {
    "animals": {
        "mammals": {
            "primates": ["human", "chimpanzee", "bonobo", "gorilla", "orangutan", "lemur", "loris"],
            "carnivora": {
                "felidae": ["lion", "tiger", "leopard", "cheetah", "lynx", "domestic cat"],
                "canidae": ["wolf", "fox", "coyote", "jackal", "dingo", "domestic dog"],
                "ursidae": ["brown bear", "polar bear", "panda", "black bear", "sloth bear"],
                "mustelidae": ["otter", "badger", "weasel", "wolverine", "polecat"],
            },
            "cetacea": ["blue whale", "humpback", "orca", "dolphin", "narwhal", "sperm whale"],
            "rodentia": ["mouse", "rat", "squirrel", "beaver", "capybara", "hamster"],
            "chiroptera": ["fruit bat", "horseshoe bat", "vampire bat", "pipistrelle"],
            "artiodactyla": ["cow", "sheep", "pig", "deer", "giraffe", "hippopotamus"],
            "proboscidea": ["african bush elephant", "asian elephant", "mammoth"],
            "marsupialia": ["kangaroo", "koala", "wombat", "opossum", "tasmanian devil"],
            "lagomorpha": ["rabbit", "hare", "pika"],
        },
        "birds": {
            "accipitriformes": ["golden eagle", "bald eagle", "sparrowhawk", "red kite", "buzzard"],
            "passeriformes": ["robin", "sparrow", "starling", "crow", "magpie", "swallow"],
            "psittaciformes": ["macaw", "cockatoo", "budgerigar", "african grey", "kea"],
            "struthioniformes": ["ostrich", "emu", "rhea", "cassowary"],
            "sphenisciformes": ["emperor penguin", "adelie penguin", "gentoo", "rockhopper"],
            "anatidae": ["mallard", "swan", "goose", "eider", "teal"],
            "columbidae": ["wood pigeon", "turtle dove", "collared dove"],
        },
        "reptiles": {
            "squamata": ["komodo dragon", "gecko", "chameleon", "python", "cobra", "viper"],
            "testudines": ["green turtle", "galapagos tortoise", "snapping turtle", "terrapin"],
            "crocodilia": ["nile crocodile", "alligator", "gharial", "caiman"],
            "rhynchocephalia": ["tuatara"],
        },
        "amphibians": {
            "anura": ["common frog", "tree frog", "cane toad", "poison dart frog", "midwife toad"],
            "caudata": ["fire salamander", "axolotl", "newt", "olm"],
            "gymnophiona": ["ringed caecilian", "rubber eel"],
        },
        "fish": {
            "chondrichthyes": ["great white shark", "hammerhead", "manta ray", "stingray", "sawfish"],
            "actinopterygii": ["salmon", "tuna", "clownfish", "seahorse", "eel", "pike"],
            "dipnoi": ["lungfish", "australian lungfish"],
        },
        "insects": {
            "hymenoptera": ["honey bee", "bumblebee", "ant", "wasp", "sawfly"],
            "lepidoptera": ["monarch", "swallowtail", "moth", "silkmoth"],
            "coleoptera": ["ladybird", "stag beetle", "firefly", "weevil", "dung beetle"],
            "diptera": ["housefly", "mosquito", "hoverfly", "cranefly"],
            "odonata": ["dragonfly", "damselfly", "hawker"],
            "orthoptera": ["grasshopper", "cricket", "locust", "katydid"],
        },
        "arachnids": {
            "araneae": ["garden spider", "tarantula", "jumping spider", "widow"],
            "scorpiones": ["emperor scorpion", "bark scorpion"],
            "acari": ["tick", "dust mite", "harvest mite"],
        },
        "crustaceans": {
            "decapoda": ["crab", "lobster", "shrimp", "prawn", "hermit crab", "crayfish"],
            "isopoda": ["woodlouse", "sea slater", "giant isopod"],
            "amphipoda": ["sand hopper", "skeleton shrimp"],
        },
        "annelids": {
            "polychaeta": ["ragworm", "fan worm", "bristleworm"],
            "clitellata": ["earthworm", "leech"],
        },
        "molluscs": {
            "cephalopoda": ["octopus", "squid", "cuttlefish", "nautilus"],
            "gastropoda": ["garden snail", "sea slug", "limpet", "whelk"],
            "bivalvia": ["mussel", "oyster", "scallop", "clam"],
        },
    }
}

#: What is already on the stack, newest first. A cut takes its branch out of the map, so
#: these are not in the tree above.
STACK: list[tuple[str, list[str]]] = [
    ("penguins", ["emperor", "adelie", "gentoo", "rockhopper"]),
    ("tuatara", []),
    ("sharks", ["great white", "hammerhead", "sawfish"]),
    ("beetles", []),
    ("primates", ["human", "gorilla", "lemur", "loris"]),
    ("cetaceans", ["blue whale", "orca", "narwhal"]),
    ("crocodilians", ["nile crocodile", "gharial"]),
    ("cephalopods", ["octopus", "cuttlefish", "nautilus"]),
]


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def clients() -> list[dict]:
    return json.loads(run(["hyprctl", "clients", "-j"]).stdout or "[]")


def node_id(index: int) -> str:
    return f"n{index:04d}"


def build_document() -> dict:
    """The taxonomy as the map file the app reads."""

    counter = 0

    def node(name: str) -> dict:
        nonlocal counter
        counter += 1
        return {"id": node_id(counter), "text": name, "collapsed": False, "mark": "", "children": []}

    def fill(parent: dict, spec: object) -> None:
        if isinstance(spec, dict):
            for name, below in spec.items():
                child = node(name)
                parent["children"].append(child)
                fill(child, below)
        else:
            for name in spec:  # type: ignore[union-attr]
                parent["children"].append(node(name))

    root = node("animals")
    fill(root, TAXONOMY["animals"])
    stack = []
    for name, children in STACK:
        entry = node(name)
        for child in children:
            entry["children"].append(node(child))
        stack.append(entry)
    return {
        "version": 1,
        "spacing": -2,
        "layout": "spider",
        "colours": "family",
        "marks": ["⭐", "❓", "✅"],
        "justify": 66,
        "cut": stack,
        "root": root,
    }


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "spoider-stack.png"
    argv = sys.argv[1:]
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])

    SCRATCH.mkdir(parents=True, exist_ok=True)
    document = SCRATCH / "animals.spoider"
    document.write_text(json.dumps(build_document(), ensure_ascii=False, indent=1), encoding="utf-8")
    cells = 0
    pending = [build_document()["root"]]
    while pending:
        one = pending.pop()
        cells += 1
        pending.extend(one["children"])
    print(f"map written with {cells} cells and {len(STACK)} cuts waiting")

    run(["pkill", "-f", f"instance-group {GROUP}"])
    run(["tmux", "kill-session", "-t", SESSION])
    time.sleep(0.5)

    kitty = subprocess.Popen(
        [
            "kitty", "--instance-group", GROUP,
            "-o", "font_family=Spleen 6x12", "-o", "font_size=9",
            "-o", "window_padding_width=0", "-o", "background_opacity=1",
            "-o", "dynamic_background_opacity=no", "-o", "background_blur=0",
            "-o", "tab_bar_style=hidden", "-o", "tab_bar_min_tabs=2",
            "-o", "confirm_os_window_close=0",
            "-T", "stackshot", "-e", "sh", "-c",
            f'tmux -f /dev/null new-session -d -s {SESSION} "cd {WORKDIR} && uv run spoider {document}";'
            f" tmux set -g status off; exec tmux attach -t {SESSION}",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
         f'hl.dispatch(hl.dsp.window.move({{ workspace = "9", window = "address:{window}" }}))'])
    run(["hyprctl", "eval",
         f'hl.dispatch(hl.dsp.window.set_prop({{ prop = "opacity", value = "1.0 1.0", window = "address:{window}" }}))'])
    run(["hyprctl", "eval", 'hl.dispatch(hl.dsp.focus({ workspace = "9" }))'])
    time.sleep(2.0)

    border = int(run(["hyprctl", "getoption", "general:border_size"]).stdout.split("int:")[1].split()[0])
    client = next(w for w in clients() if w["address"] == window)
    inner_w = client["size"][0] - 2 * border
    inner_h = client["size"][1] - 2 * border

    # Measure the cell from whatever grid the window happens to have, then fill the window.
    run(["tmux", "set", "-g", "window-size", "manual"])
    grid = run(["tmux", "display", "-p", "-t", SESSION, "#{client_width}x#{client_height}"]).stdout.strip()
    cols_now, rows_now = (int(part) for part in grid.split("x"))
    cell_w = inner_w / cols_now
    cell_h = inner_h / rows_now
    cols, rows = int(inner_w // cell_w), int(inner_h // cell_h)
    print(f"cell {cell_w:.2f}x{cell_h:.2f} -> pane {cols}x{rows} in {inner_w}x{inner_h}")
    run(["tmux", "resize-window", "-t", SESSION, "-x", str(cols), "-y", str(rows)])
    time.sleep(1.5)

    for _ in range(30):
        time.sleep(0.5)
        if "animals" in run(["tmux", "capture-pane", "-p", "-t", SESSION]).stdout:
            break
    time.sleep(1.0)
    # open the stack panel; `p` toggles it
    run(["tmux", "send-keys", "-t", SESSION, "-l", "--", "p"])
    time.sleep(2.0)

    x = client["at"][0] + border
    y = client["at"][1] + border
    width = int(cols * cell_w)
    height = int(rows * cell_h)
    shot = run(["grim", "-g", f"{x},{y} {width}x{height}", "-t", "png", str(out)])
    if shot.returncode != 0:
        print("grim failed:", shot.stderr.strip())
        return 1
    print(f"{out} {width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
