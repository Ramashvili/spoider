"""Put a tune under the tour, looping it seamlessly.

  python3 music.py --music ~/Music/tune.mp3 --video ../spoider-tour.mp4 \
      --out ../spoider-tour-with-music.mp4

A thirty-second loop played five times would click four times if the tune's tail does not
match its head, and a crossfade at each join inside one file cannot fix that. So the tune
is folded into a real loop first: its last `--cross` seconds fade into its first
`--cross` seconds, and the result is what gets repeated. The seam is then measured, not
assumed: two copies are decoded and the sample jump at the join is compared with the
largest jump inside the music itself.
"""

from __future__ import annotations

import argparse
import array
import subprocess
import sys
import tempfile
from pathlib import Path


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)]).stdout.strip()
    return float(out)


def build_loop(music: Path, crossfade: float, target: Path) -> float:
    """The tune with its tail folded into its head, ready to be repeated."""
    length = duration(music)
    if crossfade <= 0 or crossfade * 2 >= length:
        raise ValueError("the crossfade has to be shorter than half the tune")
    body = length - crossfade
    graph = (
        f"[0:a]atrim=start=0:end={body},asetpts=N/SR/TB[head];"
        f"[0:a]atrim=start={body},asetpts=N/SR/TB,afade=t=out:st=0:d={crossfade}:curve=qsin[tail];"
        f"[head]asplit=2[h1][h2];"
        f"[h1]atrim=start=0:end={crossfade},asetpts=N/SR/TB,afade=t=in:st=0:d={crossfade}:curve=qsin[front];"
        f"[front][tail]amix=inputs=2:duration=first:normalize=0[blend];"
        f"[h2]atrim=start={crossfade},asetpts=N/SR/TB[rest];"
        f"[blend][rest]concat=n=2:v=0:a=1[out]"
    )
    result = run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(music),
                  "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(target)])
    if result.returncode != 0:
        raise SystemExit(f"building the loop failed: {result.stderr[-400:]}")
    return duration(target)


def seam(path: Path) -> tuple[float, float]:
    """(jump at the join, largest jump anywhere in the music), in sample units."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "44100", "-"],
        capture_output=True,
    )
    if raw.returncode != 0:
        raise SystemExit(f"decoding failed: {raw.stderr[-300:].decode('utf-8', 'replace')}")
    data = array.array("h")
    data.frombytes(raw.stdout)
    samples = len(data)
    jumps = [abs(data[i] - data[i - 1]) for i in range(1, samples)]
    worst_inside = max(jumps)
    # the seam is the step from the last sample back to the first one
    wrap = abs(data[0] - data[-1])
    return wrap, worst_inside


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--music", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cross", type=float, default=0.30)
    parser.add_argument("--fade-in", type=float, default=1.5)
    parser.add_argument("--fade-out", type=float, default=3.0)
    parser.add_argument("--bitrate", default="128k")
    args = parser.parse_args()

    total = duration(args.video)
    with tempfile.TemporaryDirectory() as tmp:
        loop = Path(tmp) / "loop.wav"
        loop_length = build_loop(args.music, args.cross, loop)
        wrap, worst = seam(loop)
        print(f"loop {loop_length:.2f}s from a {duration(args.music):.2f}s tune "
              f"(crossfade {args.cross}s)")
        print(f"seam step {wrap} vs the largest step inside the music {worst} "
              f"({100 * wrap / worst:.0f}%)")

        fade_out_start = max(0.0, total - args.fade_out)
        graph = (
            f"[1:a]atrim=0:{total:.3f},asetpts=N/SR/TB,"
            f"afade=t=in:st=0:d={args.fade_in},"
            f"afade=t=out:st={fade_out_start:.3f}:d={args.fade_out}[a]"
        )
        result = run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(args.video),
                      "-stream_loop", "-1", "-i", str(loop),
                      "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
                      "-c:v", "copy", "-c:a", "aac", "-b:a", args.bitrate,
                      "-shortest", "-movflags", "+faststart", str(args.out)])
        if result.returncode != 0:
            raise SystemExit(f"muxing failed: {result.stderr[-400:]}")

    size = args.out.stat().st_size / 1_000_000
    print(f"written {args.out} ({size:.1f} MB, {total:.1f}s of video)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
