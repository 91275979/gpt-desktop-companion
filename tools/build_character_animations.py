"""Build transparent, loopable PNG animations from approved character stills.

The input artwork belongs in ``assets/characters/sources/<state>.png``.  This
script never invents an expression: each clip keeps the expression in its
source image and adds restrained breathing, body sway, hair-tip lag, and (for
angry states) a small deterministic tremble.  Blink uses the actual idle and
blink artwork to make a short eye-close transition.  For optional lip motion,
provide a matching ``talk_closed.png`` and ``--mouth-box``.

The generated numbered PNGs can be consumed directly by ``character.py``.
Use the project's Python environment after ``pip install Pillow`` if needed.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:
    raise SystemExit("Pillow is required: python -m pip install Pillow") from exc


ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = ROOT / "assets" / "characters"
STATES = (
    "idle", "blink", "happy", "talk", "thinking", "embarrassed",
    "shy_angry", "angry", "strong_angry", "sleep",
)
FPS = {
    "idle": 6, "happy": 8, "talk": 12, "thinking": 6,
    "embarrassed": 8, "shy_angry": 10, "angry": 12,
    "strong_angry": 12, "sleep": 4,
}
# Repeating fixed sequence; no random sampling or dependence on wall time.
TREMBLE = (0, 1, -1, 2, -2, 1, 0, -1, 2, -2, 1, -1)
# Tuned for the provided seated character; override if replacing the art.
DEFAULT_MOUTH_BOX = (0.44, 0.405, 0.56, 0.47)


def fps_for(state: str, frame_count: int) -> int:
    # The application's blink state lasts 160 ms, so show the whole clip.
    return round(frame_count / 0.16) if state == "blink" else FPS[state]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=CHARACTERS / "sources",
                        help="Directory of approved transparent state stills")
    parser.add_argument("--output", type=Path, default=CHARACTERS / "animations",
                        help="Destination of state frame directories")
    parser.add_argument("--states", default=",".join(STATES),
                        help="Comma-separated subset of states to build")
    parser.add_argument("--frames", type=int, default=12,
                        help="Frames per loop (8 to 12; default 12)")
    parser.add_argument("--height", type=int, default=768,
                        help="Output PNG canvas height in pixels (default 768)")
    parser.add_argument("--mouth-box", nargs=4, type=float,
                        default=DEFAULT_MOUTH_BOX,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="Talk mouth area as fractions of visible bounds")
    parser.add_argument("--no-webp", action="store_true",
                        help="Skip small animated WebP previews")
    args = parser.parse_args()
    args.states = tuple(dict.fromkeys(s.strip() for s in args.states.split(",") if s.strip()))
    unknown = set(args.states) - set(STATES)
    if unknown:
        parser.error(f"Unknown states: {', '.join(sorted(unknown))}")
    if not args.states:
        parser.error("At least one state is required")
    if not 8 <= args.frames <= 12:
        parser.error("--frames must be between 8 and 12")
    if not 128 <= args.height <= 1024:
        parser.error("--height must be between 128 and 1024")
    if args.mouth_box and not (
        0 <= args.mouth_box[0] < args.mouth_box[2] <= 1
        and 0 <= args.mouth_box[1] < args.mouth_box[3] <= 1
    ):
        parser.error("--mouth-box must be four increasing fractions within 0..1")
    return args


def read_art(path: Path) -> Image.Image:
    if not path.is_file():
        raise ValueError(f"Missing state artwork: {path}")
    with Image.open(path) as opened:
        rgba = opened.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getbbox() is None:
        raise ValueError(f"Completely transparent state artwork: {path}")
    if alpha.getextrema()[0] == 255:
        raise ValueError(f"State artwork needs a transparent background: {path}")
    return rgba


def bounds(image: Image.Image) -> tuple[int, int, int, int]:
    # A threshold ignores stray, nearly transparent pixels at the edges.
    mask = image.getchannel("A").point(lambda a: 255 if a >= 12 else 0)
    return mask.getbbox() or image.getchannel("A").getbbox()


def align_sources(art: dict[str, Image.Image], canvas_height: int
                  ) -> tuple[dict[str, Image.Image], tuple[int, int]]:
    """Normalize source canvas sizes and lock visible feet to one baseline."""
    margin = max(8, round(canvas_height * 0.045))
    reference_height = canvas_height - 2 * margin
    resized: dict[str, Image.Image] = {}
    for name, image in art.items():
        scale = reference_height / image.height
        size = (max(1, round(image.width * scale)), reference_height)
        resized[name] = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
    max_width = max(image.width for image in resized.values())
    canvas_size = (max_width + 2 * margin, canvas_height)
    baseline = canvas_size[1] - margin
    aligned = {}
    for name, image in resized.items():
        left, _, right, bottom = bounds(image)
        position = (round(canvas_size[0] / 2 - (left + right) / 2), baseline - bottom)
        canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        canvas.alpha_composite(image, position)
        aligned[name] = canvas
    return aligned, canvas_size


def frame_motion(state: str, index: int, count: int, size: tuple[int, int]):
    """Return smooth, cyclic deformations in source-pixel units."""
    w, h = size
    phase = math.tau * index / count
    calm = state in {"idle", "happy", "talk", "thinking", "sleep", "blink"}
    breath = (0.010 if calm else 0.005) * (1 - math.cos(phase)) / 2
    if state == "sleep":
        breath = 0.018 * (1 - math.cos(phase)) / 2
    sway = (0 if state in {"sleep", "blink"} else 0.010 * w * math.sin(phase))
    bob = (0.005 if state == "happy" else 0.003) * h * math.sin(phase)
    if state == "sleep":
        bob = 0
    hair_lag = (0.006 if calm else 0.004) * w * math.sin(phase - 0.65)
    jitter = 0.0
    if state in {"shy_angry", "angry", "strong_angry"}:
        amplitude = {"shy_angry": 0.003, "angry": 0.005, "strong_angry": 0.008}[state]
        jitter = TREMBLE[index % len(TREMBLE)] * amplitude * w
    return breath, sway, bob, hair_lag, jitter


def deform(source: Image.Image, state: str, index: int, count: int,
           visible: tuple[int, int, int, int]) -> Image.Image:
    """Warp a small grid, so the top sways while the feet stay anchored.

    Extra phase lag near both outer edges gives long hair a softer motion than
    the central body.  This uses Pillow's mesh transform, preserving RGBA.
    """
    w, h = source.size
    left, top, right, bottom = visible
    breath, sway, bob, hair_lag, jitter = frame_motion(state, index, count, source.size)
    center = (left + right) / 2
    half_width = max(1, (right - left) / 2)
    visible_height = max(1, bottom - top)

    def source_point(x: int, y: int) -> tuple[float, float]:
        upper = min(1.0, max(0.0, (bottom - y) / visible_height))
        edge = min(1.0, abs(x - center) / half_width)
        # Upper torso/head sway, with a phase-delayed movement on long side hair.
        dx = sway * upper ** 1.4 + hair_lag * edge ** 2 * upper ** 0.7 + jitter
        sy = bottom + (y - bottom) / (1 + breath) - bob * upper
        return x - dx, sy

    cell = max(64, round(min(w, h) / 9))
    xs = list(range(0, w, cell)) + [w]
    ys = list(range(0, h, cell)) + [h]
    mesh = []
    for y0, y1 in zip(ys, ys[1:]):
        for x0, x1 in zip(xs, xs[1:]):
            # Pillow QUAD order: upper-left, lower-left, lower-right, upper-right.
            p00 = source_point(x0, y0)
            p01 = source_point(x0, y1)
            p11 = source_point(x1, y1)
            p10 = source_point(x1, y0)
            mesh.append(((x0, y0, x1, y1), (*p00, *p01, *p11, *p10)))
    return source.transform(source.size, Image.Transform.MESH, mesh,
                            resample=Image.Resampling.BICUBIC,
                            fillcolor=(0, 0, 0, 0))


def with_mouth_motion(open_art: Image.Image, closed_art: Image.Image | None,
                      mouth_box: list[float] | None, index: int, count: int) -> Image.Image:
    if closed_art is None or mouth_box is None:
        return open_art
    left, top, right, bottom = bounds(open_art)
    x0 = round(left + mouth_box[0] * (right - left))
    y0 = round(top + mouth_box[1] * (bottom - top))
    x1 = round(left + mouth_box[2] * (right - left))
    y1 = round(top + mouth_box[3] * (bottom - top))
    mask = Image.new("L", open_art.size, 0)
    ImageDraw.Draw(mask).ellipse((x0, y0, x1, y1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(2, round((y1 - y0) * 0.08))))
    # 2-3 mouth pulses per loop, with a repeated end frame for a clean loop.
    close_amount = max(0.0, math.sin(math.tau * index * 2 / count)) ** 2
    mask = mask.point(lambda value: round(value * close_amount))
    return Image.composite(closed_art, open_art, mask)


def blink_art(idle: Image.Image, blink: Image.Image, index: int, count: int) -> Image.Image:
    # One fast open-close-open movement; the full clip lasts about 160 ms.
    middle = (count - 1) / 2
    closed_amount = max(0.0, 1 - abs(index - middle) / max(1, middle - 1))
    return Image.blend(idle, blink, closed_amount)


def emotion_effects(frame: Image.Image, state: str, index: int, count: int) -> Image.Image:
    """Draw animated, code-native comic symbols without obscuring the face.

    Keep every effect inside the existing character extent so the runtime's
    shared clip bounds do not shrink the character to accommodate a symbol.
    """
    if state not in {"thinking", "sleep", "shy_angry", "angry", "strong_angry"}:
        return frame
    w, h = frame.size
    phase = math.tau * index / count
    layer = Image.new("RGBA", frame.size)
    draw = ImageDraw.Draw(layer)
    font_path = Path("C:/Windows/Fonts/arialbd.ttf")

    def lettering(text, x, y, size, fill):
        font = (ImageFont.truetype(str(font_path), round(size)) if font_path.exists()
                else ImageFont.load_default(size=round(size)))
        draw.text((round(x), round(y)), text, font=font, anchor="mm", fill=fill,
                  stroke_width=max(2, round(h * .0035)),
                  stroke_fill=(40, 44, 63, round(fill[3] * .92)))

    if state == "thinking":
        lettering("?", w * .23, h * .225 + h * .008 * math.sin(phase),
                  h * .115, (235, 242, 255, 255))
        return Image.alpha_composite(frame, layer)
    if state == "sleep":
        # Three staggered Zs drift upward and fade smoothly at the loop seam.
        for n in range(3):
            p = (index / count + n / 3) % 1
            alpha = round(255 * math.sin(math.pi * p) ** .55)
            lettering("z" if p < .45 else "Z", w * (.73 + .13 * p),
                      h * (.30 - .17 * p), h * (.045 + .035 * p),
                      (209, 223, 255, alpha))
        # Apply the letter opacity to its dark outline as well.
        return Image.alpha_composite(frame, layer)

    strength = {"shy_angry": 1, "angry": 2, "strong_angry": 3}[state]
    pulse = 1 + .10 * math.sin(phase * 2)
    cx, cy = w * .25, h * .235
    radius = h * (.032 + .005 * strength) * pulse
    width = max(3, round(h * (.004 + .001 * strength)))
    # Four rounded inward hooks form the familiar anime vein/anger symbol.
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        points = [(cx + sx * radius, cy + sy * radius * .18),
                  (cx + sx * radius * .50, cy + sy * radius * .27),
                  (cx + sx * radius * .27, cy + sy * radius * .50),
                  (cx + sx * radius * .18, cy + sy * radius)]
        draw.line(points, fill=(255, 226, 217, 250), width=width + 4, joint="curve")
        draw.line(points, fill=(232, 66, 75, 255), width=width, joint="curve")
        for x, y in (points[0], points[-1]):
            r = width / 2
            draw.ellipse((x-r, y-r, x+r, y+r), fill=(232, 66, 75, 255))
    if strength >= 2:
        for side in ([-1] if strength == 2 else [-1, 1]):
            cx = w * (.16 if side < 0 else .84)
            cy = h * .405
            fw = w * (.080 if strength == 2 else .095)
            fh = h * (.11 if strength == 2 else .14)
            flicker = .07 * math.sin(phase * 2 + side)
            shape = [(0, .5), (-.46, .3), (-.5, .04), (-.29, -.26),
                     (-.24, -.04), (.02 + flicker, -.60), (.13, -.22),
                     (.34, -.39), (.46, -.03), (.47, .23), (.25, .45)]
            points = [(cx + x * fw, cy + y * fh) for x, y in shape]
            draw.polygon(points, fill=(250, 89, 53, 230))
            draw.line(points + [points[0]], fill=(255, 206, 133, 255),
                      width=max(2, round(h * .003)), joint="curve")
            core = [(-.23, .25), (-.16, .02), (.03, -.25), (.08, -.04),
                    (.22, .11), (.19, .33), (0, .42)]
            draw.polygon([(cx + x * fw, cy + y * fh) for x, y in core],
                         fill=(255, 222, 121, 255))
    return Image.alpha_composite(frame, layer)


def save_contact_sheet(first_frames: dict[str, Image.Image], output: Path) -> None:
    thumb_h, label_h, columns = 260, 28, 5
    thumb_w = round(thumb_h * next(iter(first_frames.values())).width
                    / next(iter(first_frames.values())).height)
    gap = 12
    rows = math.ceil(len(first_frames) / columns)
    sheet = Image.new("RGB", (columns * (thumb_w + gap) + gap,
                              rows * (thumb_h + label_h + gap) + gap), (30, 33, 39))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for n, (name, image) in enumerate(first_frames.items()):
        col, row = n % columns, n // columns
        x = gap + col * (thumb_w + gap)
        y = gap + row * (thumb_h + label_h + gap)
        thumb = image.copy()
        thumb.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        panel = Image.new("RGBA", (thumb_w, thumb_h), (46, 49, 56, 255))
        panel.alpha_composite(thumb, ((thumb_w - thumb.width) // 2,
                                      thumb_h - thumb.height))
        sheet.paste(panel.convert("RGB"), (x, y))
        draw.text((x + 5, y + thumb_h + 4), name, fill=(240, 240, 245), font=font)
    path = output / "contact_sheet.png"
    temporary = path.with_name(path.name + ".part")
    sheet.save(temporary, format="PNG", optimize=True)
    temporary.replace(path)


def build(args: argparse.Namespace) -> None:
    sources = args.sources.resolve()
    output = args.output.resolve()
    needed = set(args.states)
    if "blink" in needed:
        needed.add("idle")
    missing = [name for name in STATES if name in needed and not (sources / f"{name}.png").is_file()]
    if missing:
        raise SystemExit("Missing source PNGs: " + ", ".join(missing)
                         + f"\nAdd approved artwork under {sources}")
    art = {name: read_art(sources / f"{name}.png") for name in STATES if name in needed}
    if "talk" in needed and args.mouth_box and (sources / "talk_closed.png").is_file():
        art["talk_closed"] = read_art(sources / "talk_closed.png")
    aligned, canvas_size = align_sources(art, args.height)
    output.mkdir(parents=True, exist_ok=True)
    first_frames = {}
    for state in args.states:
        state_dir = output / state
        state_dir.mkdir(parents=True, exist_ok=True)
        base = aligned[state]
        clip = []
        for index in range(args.frames):
            if state == "blink":
                source = blink_art(aligned["idle"], base, index, args.frames)
            elif state == "talk":
                source = with_mouth_motion(base, aligned.get("talk_closed"),
                                           args.mouth_box, index, args.frames)
            else:
                source = base
            frame = deform(source, state, index, args.frames, bounds(base))
            frame = emotion_effects(frame, state, index, args.frames)
            frame_path = state_dir / f"{index:03d}.png"
            temporary = frame_path.with_name(frame_path.name + ".part")
            frame.save(temporary, format="PNG", optimize=True)
            temporary.replace(frame_path)
            clip.append(frame)
        for stale in state_dir.iterdir():
            if re.fullmatch(r"\d{3}\.png", stale.name) and int(stale.stem) >= args.frames:
                stale.unlink()
        # The blink clip starts open; show its closed midpoint in the sheet.
        first_frames[state] = clip[len(clip) // 2] if state == "blink" else clip[0]
        if not args.no_webp:
            previews = []
            for frame in clip:
                preview = frame.copy()
                preview.thumbnail((360, 360), Image.Resampling.LANCZOS)
                previews.append(preview)
            duration = round(1000 / fps_for(state, args.frames))
            preview_path = state_dir / "preview.webp"
            temporary = preview_path.with_name(preview_path.name + ".part")
            previews[0].save(temporary, format="WEBP", save_all=True,
                             append_images=previews[1:], duration=duration,
                             loop=0, lossless=True, method=4)
            temporary.replace(preview_path)
        print(f"{state}: {args.frames} PNG frames, {fps_for(state, args.frames)} fps")
    # Keep rates for other states when building a subset; never remove clips.
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
    else:
        manifest = {}
    previous_rates = manifest.get("fps") if isinstance(manifest.get("fps"), dict) else {}
    manifest = {
        "default_fps": 8,
        "fps": {**previous_rates, **{state: fps_for(state, args.frames) for state in args.states}},
        "frame_count": args.frames,
        "canvas": list(canvas_size),
    }
    temporary = manifest_path.with_name(manifest_path.name + ".part")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(manifest_path)
    save_contact_sheet(first_frames, output)
    print(f"Saved animations and contact sheet in {output}")


if __name__ == "__main__":
    build(parse_args())
