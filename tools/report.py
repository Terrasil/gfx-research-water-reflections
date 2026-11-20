"""Aggregate matched cases. Raw captures remain the source of every quality metric."""
from __future__ import annotations
import csv
import json
import shutil
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from protocol import STUDY, checksums, dump


def read_rows(path):
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))


def table(path,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def interval(values,seed=8041):
    """Descriptive paired bootstrap of the specified independent units only."""
    a=np.asarray(values,dtype=float)
    if len(a)<2:
        return (None,None)
    rng=np.random.default_rng(seed)
    samples=rng.choice(a,size=(5000,len(a)),replace=True).mean(axis=1)
    return tuple(float(x) for x in np.quantile(samples,[.025,.975]))


def fmt(value):
    return "n/a" if value is None else f"{value:.4f}"


def tex_text(value):
    chars={"\\":r"\textbackslash{}", "&":r"\&","%":r"\%","#":r"\#","_":r"\_",
           "$":r"\$","{":r"\{","}":r"\}","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}
    return "".join(chars.get(c,c) for c in str(value))


def panel(root,case,budget,output):
    a=STUDY["methods"][STUDY["baseline"]]
    b=STUDY["methods"][STUDY["candidate"]]
    path=root/"quality"/case["id"]
    tiles=[("Geometry reference",path/"reference_signal.png"),(a,path/f"b{budget}"/a/"signal.png"),
           (b,path/f"b{budget}"/b/"signal.png"),("Candidate absolute error",path/f"b{budget}"/b/"error.png")]
    with Image.open(tiles[0][1]) as example:
        w,h=example.size
    image=Image.new("RGB",(2*w,2*(h+24)),"white")
    draw=ImageDraw.Draw(image)
    for i,(label,file) in enumerate(tiles):
        x=(i%2)*w; y=(i//2)*(h+24)
        with Image.open(file) as tile: image.paste(tile.convert("RGB"),(x,y+24))
        draw.text((x+5,y+5),label,fill="black")
    image.save(output)


def audit_quality(case, directory, rows):
    from metrics import method_check, reference_check, summarize
    with np.load(directory/"reference.npz",allow_pickle=False) as data:
        reference,refdiag=data["signal"],data["details"]
        names=("valid","edge","contact","border") if STUDY["kind"]=="ao" else ("valid","sky","offscreen","hidden","visible")
        region={k:data[k] for k in names}
        shifts=data["reference_shifts"] if "reference_shifts" in data else None
        audit=reference_check(reference,region,shifts,refdiag,case["scene"])
    for row in rows:
        with np.load(directory/("b"+row["budget"])/row["method"]/"raw.npz",allow_pickle=False) as raw:
            signal,diag=raw["signal"],raw["details"]
            method_check(signal,diag,reference,region,case["scene"])
            computed=audit | summarize(signal,diag,reference,region,refdiag)
        for key,value in computed.items():
            matches=(row[key]=="") if value is None else row[key]!="" and np.isclose(float(row[key]),value,rtol=2e-6,atol=2e-7)
            if not matches:
                raise ValueError(f"Metric mismatch in {case['id']} / {row['method']} / {key}")


def analyze(root,paper,verify=True,manifest=None):
    root=root.resolve()
    if manifest is None:
        manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    plan=manifest["plan"]
    if manifest["study"]!=STUDY["id"] or manifest["status"]!="complete":
        raise ValueError("A complete run of this study is required")
    folder=root/"report"
    folder.mkdir(exist_ok=True)
    tables={}
    for phase in ("quality","timing"):
        rows=[]
        for case in plan[phase]:
            path=root/phase/case["id"]
            if verify and checksums(path)!=json.loads((path/"checksums.json").read_text()):
                raise ValueError(f"Capture checksum mismatch in {case['id']}")
            block=read_rows(path/(phase+".csv"))
            expected=len(STUDY["methods"])*(len(case["budgets"]) if phase=="quality" else plan["blocks"]*plan["measured"])
            if len(block)!=expected: raise ValueError(f"Incomplete {phase} table for {case['id']}")
            if verify and phase=="quality":
                audit_quality(case,path,block)
            rows.extend(block)
        table(folder/(phase+".csv"),rows)
        tables[phase]=rows
    baseline=STUDY["methods"][STUDY["baseline"]]
    candidate=STUDY["methods"][STUDY["candidate"]]
    endpoint=STUDY["primary_metric"]
    pairs=defaultdict(dict)
    for r in tables["quality"]:
        pairs[(r["case"],r["budget"])][r["method"]]=r
    guardrail=STUDY["guardrail"]
    diffs=[]
    for (key,budget),methods in pairs.items():
        a,b=methods[baseline],methods[candidate]
        diff=float(b[endpoint])-float(a[endpoint]) if a[endpoint] and b[endpoint] else None
        guard=float(b[guardrail])-float(a[guardrail]) if a[guardrail] and b[guardrail] else None
        diffs.append(dict(case=key,scene=a["scene"],view=a["view"],parameter=a["parameter"],
                          budget=budget,metric=endpoint,candidate_minus_baseline=diff,guardrail=guardrail,guardrail_delta=guard))
    table(folder/"paired_quality.csv",diffs)
    timed=defaultdict(list)
    for r in tables["timing"]:
        timed[(r["case"],r["block"],r["method"])].append(int(r["gpu_ns"])/1e6)
    time_summary=[]
    block_diffs=defaultdict(list)
    for (key,block,method),values in timed.items():
        median=statistics.median(values)
        p95=float(np.quantile(values,.95))
        time_summary.append(dict(case=key,block=block,method=method,median_ms=median,p95_ms=p95,n=len(values)))
        if method==candidate:
            block_diffs[key].append(median-statistics.median(timed[key,block,baseline]))
    table(folder/"timing_blocks.csv",time_summary)
    time_pairs=[]
    for key,deltas in block_diffs.items():
        lo,hi=interval(deltas)
        time_pairs.append(dict(case=key,delta_ms=statistics.mean(deltas),ci_low_ms=lo,ci_high_ms=hi,blocks=len(deltas)))
    table(folder/"paired_timing.csv",time_pairs)
    # Primary compare at high budget and second parameter. The tilted panel has zero wave slope.
    high=max(int(r["budget"]) for r in diffs)
    primary=[]
    for scene in STUDY["scenes"][:-1]:
        p=0.0 if scene=="tilted-metal" else STUDY["primary_parameter"]
        values=[r["candidate_minus_baseline"] for r in diffs if r["scene"]==scene and
                float(r["parameter"])==p and int(r["budget"])==high and r["candidate_minus_baseline"] is not None]
        if values: primary.append((scene,statistics.mean(values)))
    guard_by_scene={}
    for scene,_ in primary:
        param=0.0 if scene=="tilted-metal" else STUDY["primary_parameter"]
        v=[r["guardrail_delta"] for r in diffs if r["scene"]==scene and float(r["parameter"])==param
           and int(r["budget"])==high and r["guardrail_delta"] is not None]
        if v: guard_by_scene[scene]=statistics.mean(v)
    main_values=[v for name,v in primary if name!="tilted-metal"]
    if not main_values: raise ValueError("No paired observations in the primary contrast")
    lo,hi=interval(main_values)
    delta=statistics.mean(main_values)
    guard=statistics.mean(v for k,v in guard_by_scene.items() if k!="tilted-metal")
    dump(folder/"summary.json",dict(profile=plan["profile"],primary_metric=endpoint,
         candidate_minus_baseline=delta,scene_bootstrap_95=[lo,hi],budget=high,scenes=dict(primary),guardrail=guardrail,guardrail_delta=guard,guardrail_by_scene=guard_by_scene))
    chosen=next(c for c in plan["quality"] if c["scene"]==STUDY["primary_scene"] and c["view"]==0
                and c["parameter"]==STUDY["primary_parameter"])
    panel(root,chosen,high,folder/"comparison.png")
    # Exact fixed timing case for illustration; all other blocks and settings are in the CSV files.
    chosen_time=next(c for c in plan["timing"] if c["scene"]==(0 if plan["profile"]=="smoke" else 1)
                     and c["view"]==0 and c["budget"]==high and c["size"]==plan["timing"][-1]["size"])
    tr=next(r for r in time_pairs if r["case"]==chosen_time["id"])
    device=tex_text(manifest["device"]["GL_RENDERER"])
    kind="software rasterizer" if manifest["device"]["software_renderer"] else "reported graphics device"
    lines=[r"\paragraph{Recorded run.}",f"Profile \\texttt{{{plan['profile']}}} on {device} ({kind}).",
           f"Quality used {chosen['size'][0]} by {chosen['size'][1]} pixels and budget {high}.",
           r"\begin{center}\small\begin{tabular}{lr}\toprule Scene & Paired difference \\ \midrule"]
    for scene,value in primary:
        lines.append(f"{tex_text(scene)} & {fmt(value)} "+r"\\")
    lines.extend([r"\midrule",f"Equal-scene mean & {fmt(delta)} "+r"\\",r"\bottomrule\end{tabular}\end{center}",
          f"The descriptive scene-resampling interval is [{fmt(lo)}, {fmt(hi)}].",
          f"At {chosen_time['size'][0]} by {chosen_time['size'][1]} on {tex_text(chosen_time['id'].split('_')[0])},",
          f"the paired pass-time difference is {fmt(tr['delta_ms'])} ms",
          f"(block interval [{fmt(tr['ci_low_ms'])}, {fmt(tr['ci_high_ms'])}] ms).",
          r"\begin{center}\includegraphics[width=\linewidth]{generated/comparison.png}\end{center}",
          "Fixed oblique view of the thin-object scene. White in the error panel corresponds to 0.25 or greater in linear units."])
    lines.extend([f"The equal-scene change in {STUDY['guardrail_label']} was {fmt(guard)}.",
                  "The tilted metal transfer scene is tabulated separately from the water-scene mean."
                  if STUDY["kind"]=="water" else "Contact is evaluated on annotated floor pixels."])
    (folder/"results.tex").write_text("\n".join(lines)+"\n",encoding="utf-8")
    if paper:
        paper=paper.resolve()
        if "% study-id "+STUDY["id"]+"\n" not in (paper/"main.tex").read_text(encoding="utf-8"):
            raise ValueError("This manuscript belongs to a different study")
        dest=paper/"generated"
        dest.mkdir(exist_ok=True)
        for name in ("comparison.png","results.tex","summary.json","paired_quality.csv","paired_timing.csv"):
            tmp=dest/(name+".tmp")
            shutil.copyfile(folder/name,tmp)
            tmp.replace(dest/name)
    print(f"Report: {folder}")
