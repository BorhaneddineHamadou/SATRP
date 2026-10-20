#!/usr/bin/env python3
"""Combine coverage.py data of a traced run into {relpath: [covered lines]}.
usage: coverage_lines.py <stack> ; reads coverage/<stack>/data/.coverage.* via the
stack's own python (data format is version-specific), writes
coverage/<stack>/covered_lines.json and a per-file summary."""
import json, os, subprocess, sys
HOME = os.path.expanduser('~')
stack = sys.argv[1]
cov_dir = f'{HOME}/satrp_mutation/coverage/{stack}'
rc = f'{cov_dir}/coveragerc'
if stack == 'openpilot':
    py = [f'{HOME}/openpilot/.venv/bin/python']; repo = f'{HOME}/openpilot/openpilot'
else:
    py = ['singularity', 'exec', f'{HOME}/sifs/python37full.sif', f'{HOME}/tfuse_venv/bin/python']; repo = f'{HOME}/transfuser_repo'
code = r'''
import coverage, json, sys, os
rc, out = sys.argv[1], sys.argv[2]
cov = coverage.Coverage(config_file=rc)
cov.combine(keep=True)
data = cov.get_data()
res = {}
for f in data.measured_files():
    lines = sorted(data.lines(f) or [])
    if lines:
        res[f] = lines
json.dump(res, open(out, 'w'))
print(len(res), 'files with executed lines')
'''
subprocess.run(py + ['-c', code, rc, f'{cov_dir}/covered_abs.json'], check=True, cwd=f'{cov_dir}/data')
d = json.load(open(f'{cov_dir}/covered_abs.json'))
# the openpilot tree is reachable both as ~/openpilot/<pkg> and ~/openpilot/openpilot/<pkg>
prefixes = [repo, os.path.dirname(repo)] if stack == 'openpilot' else [repo]
rel = {}
for k, v in d.items():
    for pre in prefixes:
        if k.startswith(pre + '/'):
            rel[os.path.relpath(k, pre)] = v
            break
json.dump(rel, open(f'{cov_dir}/covered_lines.json', 'w'))
for k, v in sorted(rel.items(), key=lambda x: -len(x[1]))[:40]:
    print(f'{len(v):5d}  {k}')
print('files:', len(rel))
