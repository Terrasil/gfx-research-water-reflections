"""Run the fixed experiment matrix or regenerate a report from a completed run."""
from __future__ import annotations
import argparse
import contextlib
import csv
import datetime as dt
import json
import os
from pathlib import Path
import platform
import random
import sys
import tempfile

from protocol import KINDS, STUDY, checksums, dump, make_plan, source_hash


@contextlib.contextmanager
def run_lock(root):
    handle = (root / ".lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"Empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def capture(renderer, case, plan, directory):
    import numpy as np
    from PIL import Image
    from metrics import masks, method_check, pixel_error, reference_check, region_image, summarize

    renderer.configure(case, plan["seed"])
    reference, refdiag, shifts = renderer.reference(plan["reference_spp_per_shift"], plan["seed"])
    pos, normal = renderer.read("scene"), renderer.read("scene",1)
    region = masks(pos,normal,refdiag)
    audit = reference_check(reference,region,shifts,refdiag,case["scene"])
    extra = {} if shifts is None else {"reference_shifts":shifts}
    np.savez_compressed(directory/"reference.npz",signal=reference,details=refdiag,
                        position_id=pos,normal_contact=normal,**extra,**region)
    renderer.set_reference_signal(reference)
    renderer.image(directory/"reference_scene.png",0)
    renderer.image(directory/"reference_signal.png",1)
    Image.fromarray(region_image(region)).save(directory/"regions.png")
    rows = []
    for budget in case["budgets"]:
        for method, name in enumerate(STUDY["methods"]):
            folder = directory/f"b{budget}"/name
            folder.mkdir(parents=True)
            renderer.draw("quality","quality",uMethod=method,uBudget=budget)
            rgba, diag = renderer.read("quality"), renderer.read("quality",1)
            signal = rgba[...,0] if STUDY["kind"]=="ao" else rgba[...,:3]
            method_check(signal,diag,reference,region,case["scene"])
            np.savez_compressed(folder/"raw.npz",signal=signal,details=diag)
            renderer.image(folder/"scene.png",0,method,budget)
            renderer.image(folder/"signal.png",1,method,budget)
            error = pixel_error(signal,reference)
            level = np.rint(255*np.clip(error/.25,0,1)).astype("uint8")
            level[~region["valid"]] = 0
            Image.fromarray(level).save(folder/"error.png")
            row = dict(case=case["id"],scene=STUDY["scenes"][case["scene"]],view=STUDY["views"][case["view"]],
                       parameter=case["parameter"],width=case["size"][0],height=case["size"][1],
                       budget=budget,method=name,**audit,**summarize(signal,diag,reference,region,refdiag))
            rows.append(row)
    write_csv(directory/"quality.csv",rows)


def time_case(renderer, case, plan, directory):
    renderer.configure(case,plan["seed"])
    rows = []
    for block in range(plan["blocks"]):
        order = list(range(len(STUDY["methods"])))
        random.Random(f"{plan['seed']}:{case['id']}:{block}").shuffle(order)
        for slot, method in enumerate(order):
            times = renderer.times(method,case["budget"],plan["warmup"],plan["measured"])
            for sample,ns in enumerate(times):
                rows.append(dict(case=case["id"],scene=STUDY["scenes"][case["scene"]],
                                 view=STUDY["views"][case["view"]],parameter=case["parameter"],
                                 width=case["size"][0],height=case["size"][1],budget=case["budget"],
                                 block=block,order=slot,sample=sample,method=STUDY["methods"][method],gpu_ns=ns))
    write_csv(directory/"timing.csv",rows)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(args):
    root = args.out.resolve()
    root.mkdir(parents=True,exist_ok=True)
    with run_lock(root):
        mf = root/"manifest.json"
        manifest = json.loads(mf.read_text()) if mf.exists() else None
        if manifest and not args.resume:
            raise ValueError("Existing run. Select a new output directory or pass --resume.")
        if not manifest and any(x.name!=".lock" for x in root.iterdir()):
            raise ValueError("Output directory already contains unrelated files")
        plan = make_plan(args.profile)
        fingerprint = source_hash()
        if manifest and (manifest["source_sha256"]!=fingerprint or manifest["plan"]!=plan):
            raise ValueError("Saved run uses a different plan or source revision")
        if not manifest:
            manifest = dict(study=STUDY["id"],started_utc=now(),source_sha256=fingerprint,
                            plan=plan,command=sys.argv[1:],hardware_note=args.hardware_note,
                            python=platform.python_version(),status="starting")
            dump(mf,manifest)
        try:
            from renderer import Renderer
            renderer = Renderer(args.backend,args.device)
            if args.expect_renderer and args.expect_renderer.lower() not in renderer.info["GL_RENDERER"].lower():
                raise ValueError(f"Requested GPU does not match {renderer.info['GL_RENDERER']}")
            if "device" in manifest and manifest["device"]!=renderer.info:
                raise ValueError("Saved run has different hardware, driver or runtime versions")
            manifest.update(status="running",device=renderer.info)
            manifest.pop("error",None)
            dump(mf,manifest)
            print(f"{STUDY['title']} | {renderer.info['GL_RENDERER']} | {root}",flush=True)
            for phase, func in (("quality",capture),("timing",time_case)):
                parent = root/phase
                parent.mkdir(exist_ok=True)
                for index, case in enumerate(plan[phase],1):
                    target = parent/case["id"]
                    print(f"{phase} {index}/{len(plan[phase])}   {case['id']}",flush=True)
                    if target.is_dir():
                        if checksums(target)!=json.loads((target/"checksums.json").read_text()):
                            raise ValueError(f"Corrupt checkpoint: {target}")
                        continue
                    with tempfile.TemporaryDirectory(dir=parent,prefix=".work-") as temp:
                        work = Path(temp)/"case"
                        work.mkdir()
                        func(renderer,case,plan,work)
                        dump(work/"checksums.json",checksums(work))
                        work.rename(target)
            manifest.update(status="complete",finished_utc=now())
            dump(mf,manifest)
        except BaseException as exc:
            if manifest.get("status")!="complete":
                manifest.update(status="interrupted",error=str(exc))
                dump(mf,manifest)
            raise
    from report import analyze
    analyze(root,None,verify=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    for name in ("run","plan"):
        p=sub.add_parser(name)
        p.add_argument("--profile",choices=KINDS,default="smoke")
        if name=="run":
            p.add_argument("--out",type=Path,required=True)
            p.add_argument("--resume",action="store_true")
            p.add_argument("--backend",choices=("auto","default","egl"),default="auto")
            p.add_argument("--device",type=int)
            p.add_argument("--expect-renderer",help="Require a substring in GL_RENDERER")
            p.add_argument("--hardware-note",default="")
    p=sub.add_parser("analyze")
    p.add_argument("run",type=Path)
    p.add_argument("--paper",type=Path,help="Import tables and image into the matching LaTeX project")
    args=parser.parse_args()
    if args.action=="plan":
        print(json.dumps(make_plan(args.profile),indent=2))
    elif args.action=="analyze":
        from report import analyze
        analyze(args.run,args.paper,verify=True)
    else:
        run(args)


if __name__=="__main__":
    main()
