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
            "primates": {
                "hominidae": {"homo": ["human"], "pan": ["chimpanzee", "bonobo"], "gorilla": ["gorilla"]},
                "cercopithecidae": {"macaca": ["rhesus", "macaque"], "papio": ["baboon", "mandrill"]},
                "lemuridae": {"lemur": ["ring-tailed lemur", "ruffed lemur"], "varecia": ["black lemur"]},
                "lorisidae": {"loris": ["slender loris"], "galago": ["bushbaby"]},
            },
            "carnivora": {
                "felidae": {
                    "panthera": {
                        "leo": ["barbary lion", "asiatic lion", "masai lion"],
                        "tigris": ["bengal tiger", "siberian tiger", "sumatran tiger"],
                        "onca": ["jaguar"],
                        "pardus": ["african leopard", "snow leopard", "amur leopard"],
                    },
                    "felis": {"silvestris": ["wildcat", "domestic cat"]},
                    "lynx": {"lynx": ["eurasian lynx"], "rufus": ["bobcat"]},
                    "acinonyx": {"jubatus": ["cheetah"]},
                },
                "canidae": {
                    "canis": {"lupus": ["grey wolf", "arctic wolf", "dingo"], "latrans": ["coyote"], "aureus": ["golden jackal"]},
                    "vulpes": {"vulpes": ["red fox"], "zerda": ["fennec"], "lagopus": ["arctic fox"]},
                    "lycaon": {"pictus": ["african wild dog"]},
                },
                "ursidae": {
                    "ursus": ["brown bear", "polar bear", "black bear"],
                    "ailuropoda": ["panda"],
                    "melursus": ["sloth bear"],
                },
                "mustelidae": {
                    "lutra": ["eurasian otter", "sea otter"],
                    "meles": ["badger"],
                    "mustela": ["weasel", "stoat", "polecat"],
                    "gulo": ["wolverine"],
                },
            },
            "cetacea": {
                "balaenopteridae": {"balaenoptera": ["blue whale", "humpback", "fin whale"]},
                "delphinidae": {"delphinus": ["common dolphin"], "orcinus": ["orca"], "tursiops": ["bottlenose"]},
                "monodontidae": {"monodon": ["narwhal"], "delphinapterus": ["beluga"]},
            },
            "rodentia": {
                "muridae": {"mus": ["house mouse"], "rattus": ["brown rat", "black rat"]},
                "sciuridae": {"sciurus": ["red squirrel", "grey squirrel"], "marmota": ["marmot"]},
                "castoridae": {"castor": ["beaver"]},
                "caviidae": {"cavia": ["guinea pig"], "hydrochoerus": ["capybara"]},
            },
            "chiroptera": {
                "pteropodidae": {"pteropus": ["flying fox", "fruit bat"]},
                "rhinolophidae": {"rhinolophus": ["horseshoe bat"]},
                "phyllostomidae": {"desmodus": ["vampire bat"]},
            },
            "artiodactyla": {
                "bovidae": {"bos": ["cow"], "ovis": ["sheep"], "capra": ["goat"], "gazella": ["gazelle"]},
                "cervidae": {"cervus": ["red deer"], "alces": ["moose"], "capreolus": ["roe deer"]},
                "giraffidae": {"giraffa": ["giraffe"], "okapia": ["okapi"]},
                "suidae": {"sus": ["wild boar", "pig"]},
            },
            "proboscidea": {"elephantidae": {"loxodonta": ["african bush elephant"], "elephas": ["asian elephant"]}},
            "marsupialia": {
                "macropodidae": {"macropus": ["kangaroo", "wallaby"]},
                "phascolarctidae": {"phascolarctos": ["koala"]},
                "dasyuridae": {"sarcophilus": ["tasmanian devil"]},
            },
            "lagomorpha": {"leporidae": {"lepus": ["hare"], "oryctolagus": ["rabbit"], "ochotona": ["pika"]}},
        },
        "birds": {
            "accipitriformes": {
                "accipitridae": {"aquila": ["golden eagle"], "haliaeetus": ["bald eagle"], "buteo": ["buzzard"], "milvus": ["red kite"]},
            },
            "passeriformes": {
                "turdidae": {"turdus": ["blackbird", "song thrush"]},
                "corvidae": {"corvus": ["rook", "carrion crow", "raven"], "pica": ["magpie"]},
                "hirundinidae": {"hirundo": ["barn swallow"]},
                "paridae": {"parus": ["great tit"]},
            },
            "psittaciformes": {
                "psittacidae": {"ara": ["scarlet macaw", "blue macaw"], "psittacus": ["african grey"]},
                "cacatuidae": {"cacatua": ["cockatoo"], "melopsittacus": ["budgerigar"]},
                "nestoridae": {"nestor": ["kea"]},
            },
            "struthioniformes": {"struthionidae": {"struthio": ["ostrich"]}, "casuariidae": {"dromaius": ["emu"], "casuarius": ["cassowary"]}},
            "sphenisciformes": {
                "spheniscidae": {
                    "aptenodytes": {"patagonicus": ["king penguin"], "forsteri": ["emperor penguin"]},
                    "pygoscelis": {"adeliae": ["adelie"], "papua": ["gentoo"]},
                    "eudyptes": {"chrysocome": ["rockhopper"]},
                },
            },
            "anatidae": {"anatidae": {"anas": ["mallard", "teal"], "cygnus": ["mute swan", "whooper"], "branta": ["brent goose"]}},
            "columbidae": {"columbidae": {"columba": ["wood pigeon"], "streptopelia": ["collared dove", "turtle dove"]}},
        },
        "reptiles": {
            "squamata": {
                "varanidae": {"varanus": ["komodo dragon", "monitor"]},
                "gekkonidae": {"gekko": ["leopard gecko"], "hemidactylus": ["house gecko"]},
                "chamaeleonidae": {"chamaeleo": ["common chameleon"]},
                "pythonidae": {"python": ["ball python", "reticulated python"]},
                "elapidae": {"naja": ["cobra"], "bungarus": ["krait"]},
                "viperidae": {"vipera": ["adder"], "crotalus": ["rattlesnake"]},
            },
            "testudines": {
                "cheloniidae": {"chelonia": ["green turtle"], "caretta": ["loggerhead"]},
                "testudinidae": {"chelonoidis": ["galapagos tortoise"], "testudo": ["hermann's tortoise"]},
                "chelydridae": {"chelydra": ["snapping turtle"]},
            },
            "crocodilia": {
                "crocodylidae": {"crocodylus": ["nile crocodile", "saltwater crocodile"]},
                "alligatoridae": {"alligator": ["american alligator"], "caiman": ["spectacled caiman"]},
                "gavialidae": {"gavialis": ["gharial"]},
            },
            "rhynchocephalia": {"sphenodontidae": {"sphenodon": ["tuatara"]}},
        },
        "amphibians": {
            "anura": {
                "ranidae": {"rana": ["common frog"], "pelophylax": ["edible frog"]},
                "hylidae": {"hyla": ["tree frog"]},
                "bufonidae": {"bufo": ["common toad"], "rhinella": ["cane toad"]},
                "dendrobatidae": {"dendrobates": ["poison dart frog"]},
            },
            "caudata": {
                "salamandridae": {"salamandra": ["fire salamander"], "triturus": ["newt"]},
                "ambystomatidae": {"ambystoma": ["axolotl"]},
                "proteidae": {"proteus": ["olm"]},
            },
            "gymnophiona": {"caeciliidae": {"caecilia": ["ringed caecilian"]}},
        },
        "fish": {
            "chondrichthyes": {
                "lamnidae": {"carcharodon": ["great white"], "isurus": ["mako"]},
                "sphyrnidae": {"sphyrna": ["hammerhead"]},
                "mobulidae": {"mobula": ["manta ray"]},
                "dasyatidae": {"dasyatis": ["stingray"]},
                "pristidae": {"pristis": ["sawfish"]},
            },
            "actinopterygii": {
                "salmonidae": {"salmo": ["atlantic salmon"], "oncorhynchus": ["sockeye"]},
                "scombridae": {"thunnus": ["bluefin tuna", "yellowfin"]},
                "pomacentridae": {"amphiprion": ["clownfish"]},
                "syngnathidae": {"hippocampus": ["seahorse"]},
                "anguillidae": {"anguilla": ["european eel"]},
                "esocidae": {"esox": ["pike"]},
            },
            "dipnoi": {"lepidosirenidae": {"lepidosiren": ["south american lungfish"]}, "neoceratodontidae": {"neoceratodus": ["australian lungfish"]}},
        },
        "molluscs": {
            "cephalopoda": {
                "octopodidae": {"octopus": ["common octopus"]},
                "loliginidae": {"loligo": ["squid"]},
                "sepiolidae": {"sepia": ["cuttlefish"]},
                "nautilidae": {"nautilus": ["chambered nautilus"]},
            },
            "gastropoda": {
                "helicidae": {"helix": ["garden snail"]},
                "dorididae": {"doris": ["sea slug"]},
                "patellidae": {"patella": ["limpet"]},
            },
            "bivalvia": {"mytilidae": {"mytilus": ["mussel"]}, "ostreidae": {"ostrea": ["oyster"]}, "pectinidae": {"pecten": ["scallop"]}},
        },
        "insects": {
            "hymenoptera": {
                "apidae": {"apis": ["honey bee"], "bombus": ["bumblebee"]},
                "formicidae": {"formica": ["wood ant"], "lasius": ["black ant"]},
                "vespidae": {"vespa": ["hornet"], "vespula": ["wasp"]},
                "tenthredinidae": {"tenthredo": ["sawfly"]},
            },
            "lepidoptera": {
                "nymphalidae": {"danaus": ["monarch"], "vanessa": ["painted lady"]},
                "papilionidae": {"papilio": ["swallowtail"]},
                "saturniidae": {"bombyx": ["silkmoth"], "saturnia": ["emperor moth"]},
            },
            "coleoptera": {
                "coccinellidae": {"coccinella": {"septempunctata": ["seven-spot ladybird"], "undecimpunctata": ["eleven-spot"]}},
                "lucanidae": {"lucanus": ["stag beetle"]},
                "lampyridae": {"lampyris": ["firefly"]},
                "curculionidae": {"curculio": ["weevil"]},
                "scarabaeidae": {"scarabaeus": ["dung beetle"]},
            },
            "diptera": {
                "muscidae": {"musca": ["housefly"]},
                "culicidae": {"culex": ["mosquito"], "anopheles": ["malaria mosquito"]},
                "syrphidae": {"syrphus": ["hoverfly"]},
                "tipulidae": {"tipula": ["cranefly"]},
            },
            "odonata": {
                "aeshnidae": {"aeshna": ["hawker"]},
                "libellulidae": {"libellula": ["dragonfly"]},
                "coenagrionidae": {"ischnura": ["damselfly"]},
            },
            "orthoptera": {
                "acrididae": {"locusta": ["locust"], "schistocerca": ["desert locust"]},
                "gryllidae": {"gryllus": ["field cricket"]},
                "tettigoniidae": {"tettigonia": ["katydid"]},
            },
        },
        "arachnids": {
            "araneae": {
                "araneidae": {"araneus": ["garden spider"]},
                "theraphosidae": {"theraphosa": ["goliath tarantula"]},
                "salticidae": {"salticus": ["jumping spider"]},
                "theridiidae": {"latrodectus": ["widow"]},
            },
            "scorpiones": {"scorpionidae": {"pandinus": ["emperor scorpion"]}, "buthidae": {"centruroides": ["bark scorpion"]}},
            "acari": {"ixodidae": {"ixodes": ["tick"]}, "pyroglyphidae": {"dermatophagoides": ["dust mite"]}},
        },
        "crustaceans": {
            "decapoda": {
                "cancridae": {"cancer": ["crab"]},
                "nephropidae": {"homarus": ["lobster"]},
                "palaemonidae": {"palaemon": ["prawn"]},
                "paguridae": {"pagurus": ["hermit crab"]},
            },
            "isopoda": {"armadillidiidae": {"armadillidium": ["woodlouse"]}, "cirolanidae": {"cirolana": ["sea slater"]}},
            "amphipoda": {"talitridae": {"talitrus": ["sand hopper"]}},
        },
        "annelids": {
            "polychaeta": {"nereididae": {"nereis": ["ragworm"]}, "sabellidae": {"sabella": ["fan worm"]}},
            "clitellata": {"lumbricidae": {"lumbricus": ["earthworm"]}, "hirudinidae": {"hirudo": ["leech"]}},
        },
    }
}

#: One rank above the classes, so the tree runs deeper without the classes being repeated.
PHYLA: dict[str, list[str]] = {
    "chordates": ["mammals", "birds", "reptiles", "amphibians", "fish"],
    "molluscs": ["molluscs"],
    "arthropods": ["insects", "arachnids", "crustaceans"],
    "annelids": ["annelids"],
}

#: What is already on the stack, newest first. A cut takes its branch out of the map, so
#: these are not in the tree above.
STACK: list[tuple[str, object]] = [
    ("penguins", {"aptenodytes": ["emperor", "king"], "pygoscelis": ["adelie", "gentoo"]}),
    ("tuatara", []),
    ("sharks", {"lamnidae": ["great white", "mako"], "sphyrnidae": ["hammerhead"]}),
    ("beetles", []),
    ("primates", {"hominidae": ["human", "gorilla"], "lemuridae": {"lemur": ["ring-tailed", "ruffed"]}}),
    ("cetaceans", ["blue whale", "orca", "narwhal"]),
    ("crocodilians", ["nile crocodile", "gharial"]),
    ("cephalopods", {"octopodidae": ["octopus"], "nautilidae": ["nautilus"]}),
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
    classes = TAXONOMY["animals"]
    assert isinstance(classes, dict)
    for phylum, members in PHYLA.items():
        branch = node(phylum)
        root["children"].append(branch)
        for name in members:
            child = node(name)
            branch["children"].append(child)
            fill(child, classes[name])
    stack = []
    for name, below in STACK:
        entry = node(name)
        fill(entry, below)
        stack.append(entry)
    return {
        "version": 1,
        "spacing": -1,
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

    try:
        return capture(kitty, document, out)
    finally:
        kitty.terminate()
        try:
            kitty.wait(timeout=10)
        except subprocess.TimeoutExpired:
            kitty.kill()
        run(["tmux", "kill-session", "-t", SESSION])
        print("window closed")


def capture(kitty: subprocess.Popen, document: Path, out: Path) -> int:
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
    # colour by depth rather than by family, then open the panel and walk to the fourth cut
    run(["tmux", "send-keys", "-t", SESSION, "-l", "--", "c"])
    time.sleep(1.2)
    run(["tmux", "send-keys", "-t", SESSION, "-l", "--", "p"])
    time.sleep(1.5)
    for _ in range(3):
        run(["tmux", "send-keys", "-t", SESSION, "-H", "0e"])
        time.sleep(0.6)
    time.sleep(1.0)
    # the fourth entry in the panel: three steps down from the newest cut
    for _ in range(3):
        run(["tmux", "send-keys", "-t", SESSION, "-H", "1b", "5b", "42"])
        time.sleep(0.35)
    time.sleep(1.0)

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
