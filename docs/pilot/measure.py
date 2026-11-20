"""Rerun the documented image-quality pilot using the project's published shaders and metrics."""
import argparse
import csv
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))

from metrics import masks, method_check, reference_check, summarize
from protocol import STUDY, make_plan
from renderer import Renderer


def measure(renderer):
    ao = STUDY['kind'] == 'ao'
    scenes = {'contacts', 'slats', 'cavity', 'frustum-edge'} if ao else {'quay', 'pilings', 'occluded-bank'}
    plan = make_plan('paper')
    seed = plan['seed']
    for case in plan['quality']:
        scene = STUDY['scenes'][case['scene']]
        if scene not in scenes or case['parameter'] != STUDY['primary_parameter']:
            continue
        budget = max(case['budgets'])
        renderer.configure(dict(case, size=[320, 180]), seed)
        reference, reference_details, shifts = renderer.reference(128, seed)
        regions = masks(renderer.read('scene'), renderer.read('scene', 1), reference_details)
        audit = reference_check(reference, regions, shifts, reference_details, case['scene'])
        for index, method in enumerate(STUDY['methods']):
            renderer.draw('quality', 'quality', uMethod=index, uBudget=budget)
            rgba = renderer.read('quality')
            signal = rgba[..., 0] if ao else rgba[..., :3]
            details = renderer.read('quality', 1)
            method_check(signal, details, reference, regions, case['scene'])
            stats = summarize(signal, details, reference, regions, reference_details)
            yield dict(scene=scene, view=STUDY['views'][case['view']], method=method, **audit, **stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='New per-view CSV file')
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'File already exists: {args.out}')
    renderer = Renderer('auto', None)
    rows = list(measure(renderer))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"{renderer.info['GL_RENDERER']} | {len(rows)} observations | {args.out}")


if __name__ == '__main__':
    main()
