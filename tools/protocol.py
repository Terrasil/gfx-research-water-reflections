from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = json.loads((ROOT / "study.json").read_text(encoding="utf-8"))
KINDS = ("smoke", "quick", "paper")


def source_hash():
    digest = hashlib.sha256()
    selected = [ROOT / "study.json", ROOT / "requirements.txt"]
    for directory in ("tools", "shaders"):
        selected.extend(p for p in (ROOT / directory).iterdir() if p.is_file())
    for path in sorted(selected):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def make_plan(profile):
    options = {
        "smoke": ((144, 80), [(144, 80)], [0], 32, 1, 2, 3),
        "quick": ((320, 180), [(640, 360)], [0, 2], 96, 3, 5, 10),
        "paper": ((640, 360), [(1280, 720), (1920, 1080)], [0, 1, 2], 512, 5, 12, 40),
    }
    quality_size, time_sizes, views, spp, blocks, warmup, measured = options[profile]
    parameters = STUDY["parameters"]
    budgets = STUDY["budgets"][:1] if profile == "smoke" else STUDY["budgets"]
    quality, timing = [], []
    for scene in range(len(STUDY["scenes"])):
        for view in views:
            null = scene == 4
            metal = STUDY["kind"] == "water" and scene == 3
            if null and view != 0:
                continue
            params = parameters if profile != "smoke" else [parameters[-1]]
            if metal or null:
                params = [parameters[0]]
            for param in params:
                token = str(param).replace(".", "p")
                key = f"{STUDY['scenes'][scene]}_{STUDY['views'][view]}_{token}"
                common = dict(scene=scene, view=view, parameter=param)
                quality.append(dict(id=key, size=list(quality_size), budgets=budgets, **common))
                if scene not in ([0] if profile == "smoke" else [0, 1]) or param != parameters[-1]:
                    continue
                for size in time_sizes:
                    for budget in budgets:
                        timing.append(dict(id=f"{key}_{size[0]}x{size[1]}_b{budget}",
                                           size=list(size), budget=budget, **common))
    return dict(schema=1, study=STUDY["id"], profile=profile, seed=17,
                reference_spp_per_shift=spp if STUDY["kind"] == "ao" else 1,
                reference_shifts=2 if STUDY["kind"] == "ao" else 1,
                blocks=blocks, warmup=warmup, measured=measured, quality=quality, timing=timing)


def dump(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def checksums(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            result[path.relative_to(directory).as_posix()] = file_hash(path)
    return result


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
