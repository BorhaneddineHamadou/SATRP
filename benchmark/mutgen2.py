#!/usr/bin/env python3
"""mutgen2 — extended surgical AST mutation generator (stdlib only).

Operators (one edit per mutant, exact source spans, stable ids
"<relpath>:<walk_idx>:<OP>[:<variant>]"):
  ROR  relational boundary swap   <-><=  >-><=  ==-><!=
  COR  boolean and<->or
  AOR  arithmetic +<->- *<->/
  CRP  int n -> n+1 (not in subscripts), True<->False
  CSC  numeric literal scaled x0.5 / x2 (floats; ints only in arithmetic/compare)
  SGN  negate the value of a return / assignment (numeric expressions only)
  CLR  remove a clamp: np.clip(x,a,b)->x, min(a,b)->a, max(a,b)->a, clamp(x,a,b)->(x, False)
  NEG  if c: -> if not (c):
  SDL  delete a simple statement (assign / augassign / call expr) -> pass
  IDX  constant subscript index shifted by one (k -> k+1, -k -> -(k+1))

Commands
  enumerate <repo> <rel_or_dir>... [--covered lines.json] > sites.json
  apply     <repo> <out_dir> <site_id> [--tree]   (copy one file, or the whole
            package dir with --tree, and apply the edit; prints old/new)
  show      <repo> <site_id>
"""
import ast, json, os, sys, shutil, hashlib

ROR_SWAP = {'<': '<=', '>': '>=', '<=': '<', '>=': '>', '==': '!=', '!=': '=='}
AOR_SWAP = {'+': '-', '-': '+', '*': '/', '/': '*'}
CMP_SYM = {ast.Lt: '<', ast.Gt: '>', ast.LtE: '<=', ast.GtE: '>=', ast.Eq: '==', ast.NotEq: '!='}
BIN_SYM = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}
CLAMP_FUNCS = {'clip', 'min', 'max', 'clamp'}
EXCLUDE_DIRS = ('tests', 'test', '.git', '__pycache__', 'examples', 'models')


def _lines(src):
    return src.split('\n')


def _seg(lines, l0, c0, l1, c1):
    if l0 == l1:
        return lines[l0 - 1][c0:c1]
    parts = [lines[l0 - 1][c0:]] + lines[l0:l1 - 1] + [lines[l1 - 1][:c1]]
    return '\n'.join(parts)


def _node_seg(lines, n):
    return _seg(lines, n.lineno, n.col_offset, n.end_lineno, n.end_col_offset)


def _gap(lines, a, b):
    """source text between end of node a and start of node b, with offsets"""
    return _seg(lines, a.end_lineno, a.end_col_offset, b.lineno, b.col_offset)


def _func_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _numeric_like(n):
    """heuristic: expression that is plausibly numeric (safe to negate)"""
    if isinstance(n, (ast.BinOp, ast.UnaryOp)):
        return True
    if isinstance(n, ast.Constant):
        return False  # negating a bare literal is CSC/CRP territory, not a sign bug
    if isinstance(n, ast.Call):
        fn = _func_name(n)
        return fn in ('interp', 'clip', 'sqrt', 'abs', 'min', 'max', 'exp', 'sin',
                      'cos', 'atan2', 'arctan2', 'radians', 'degrees', 'float',
                      'norm', 'mean', 'sum', 'clamp', 'update', 'step', 'calc_curvature')
    if isinstance(n, ast.Attribute):
        return n.attr.startswith(('v', 'a_', 'x', 'y', 'k', 'K', 'dt', 'speed',
                                  'accel', 'curv', 'angle', 'steer', 'torque'))
    return False


def _in_subscript(node, parents):
    p = parents.get(id(node))
    while p is not None:
        if isinstance(p, ast.Subscript):
            return True
        if isinstance(p, (ast.stmt,)):
            return False
        p = parents.get(id(p))
    return False


def _parent_map(tree):
    pm = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            pm[id(c)] = p
    return pm


def _fmt_num(v):
    if isinstance(v, float):
        s = repr(v)
        return s
    return str(v)


def file_sites(repo, rel, covered=None):
    """Return list of site dicts for one file. covered: set of line numbers or None."""
    path = os.path.join(repo, rel)
    src = open(path, encoding='utf-8').read()
    lines = _lines(src)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    pm = _parent_map(tree)
    sites = []
    idx = 0

    def add(node, op, l0, c0, l1, c1, new, variant=None, note=''):
        if covered is not None and l0 not in covered:
            return
        old = _seg(lines, l0, c0, l1, c1)
        sid = f"{rel}:{idx}:{op}" + (f":{variant}" if variant else '')
        sites.append(dict(id=sid, file=rel, line=l0, op=op, old=old, new=new,
                          span=[l0, c0, l1, c1], note=note))

    for node in ast.walk(tree):
        idx += 1
        # --- ROR
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in CMP_SYM:
            sym = CMP_SYM[type(node.ops[0])]
            gap = _gap(lines, node.left, node.comparators[0])
            k = gap.find(sym)
            if k >= 0 and node.left.end_lineno == node.comparators[0].lineno:
                c0 = node.left.end_col_offset + k
                add(node, 'ROR', node.left.end_lineno, c0, node.left.end_lineno, c0 + len(sym), ROR_SWAP[sym])
        # --- AOR
        if isinstance(node, ast.BinOp) and type(node.op) in BIN_SYM:
            sym = BIN_SYM[type(node.op)]
            gap = _gap(lines, node.left, node.right)
            k = gap.find(sym)
            if k >= 0 and node.left.end_lineno == node.right.lineno and sym + '=' not in gap:
                c0 = node.left.end_col_offset + k
                if lines[node.left.end_lineno - 1][c0:c0 + 2] not in ('**', '//'):
                    add(node, 'AOR', node.left.end_lineno, c0, node.left.end_lineno, c0 + 1, AOR_SWAP[sym])
        # --- COR
        if isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            sym = 'and' if isinstance(node.op, ast.And) else 'or'
            a, b = node.values[0], node.values[1]
            gap = _gap(lines, a, b)
            k = gap.find(sym)
            if k >= 0 and a.end_lineno == b.lineno:
                c0 = a.end_col_offset + k
                add(node, 'COR', a.end_lineno, c0, a.end_lineno, c0 + len(sym), 'or' if sym == 'and' else 'and')
        # --- constants: CRP / CSC / IDX
        if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float)):
            v = node.value
            insub = _in_subscript(node, pm)
            par = pm.get(id(node))
            if isinstance(v, bool):
                add(node, 'CRP', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, str(not v))
            elif isinstance(v, int):
                if insub:
                    # IDX: k -> k+1 ; handles negative via parent UnaryOp(-)
                    neg = isinstance(par, ast.UnaryOp) and isinstance(par.op, ast.USub)
                    if v >= 0:
                        add(node, 'IDX', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset,
                            str(v + 1), note='neg' if neg else '')
                else:
                    if v not in (0, 1):
                        add(node, 'CRP', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, str(v + 1))
                    if v not in (0,) and isinstance(par, (ast.BinOp, ast.Compare, ast.Assign, ast.Call, ast.keyword, ast.Return)):
                        add(node, 'CSC', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, str(v * 2), variant='x2')
                        if v % 2 == 0 and v >= 2:
                            add(node, 'CSC', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, str(v // 2), variant='x05')
            else:  # float
                if not insub and v != 0.0:
                    add(node, 'CSC', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, _fmt_num(v * 2), variant='x2')
                    add(node, 'CSC', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, _fmt_num(v * 0.5), variant='x05')
        # --- SGN
        if isinstance(node, ast.Return) and node.value is not None and _numeric_like(node.value):
            add(node, 'SGN', node.value.lineno, node.value.col_offset, node.value.end_lineno, node.value.end_col_offset,
                '-(' + _node_seg(lines, node.value) + ')')
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and _numeric_like(node.value):
            add(node, 'SGN', node.value.lineno, node.value.col_offset, node.value.end_lineno, node.value.end_col_offset,
                '-(' + _node_seg(lines, node.value) + ')')
        # --- CLR
        if isinstance(node, ast.Call) and _func_name(node) in CLAMP_FUNCS and len(node.args) >= 2:
            fn = _func_name(node)
            a0 = _node_seg(lines, node.args[0])
            if fn == 'clamp':
                new = '(' + a0 + ', False)'
            elif fn in ('min', 'max') and len(node.args) == 2:
                new = '(' + a0 + ')'
            elif fn == 'clip' and len(node.args) >= 3:
                new = '(' + a0 + ')'
            else:
                new = None
            if new:
                add(node, 'CLR', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, new, note=fn)
        # --- NEG
        if isinstance(node, ast.If):
            t = node.test
            add(node, 'NEG', t.lineno, t.col_offset, t.end_lineno, t.end_col_offset, 'not (' + _node_seg(lines, t) + ')')
        # --- SDL
        if isinstance(node, (ast.Assign, ast.AugAssign)) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            par = pm.get(id(node))
            if isinstance(par, (ast.FunctionDef, ast.If, ast.For, ast.While, ast.With, ast.Else if hasattr(ast, 'Else') else ast.If)) \
                    and node.lineno == node.end_lineno:
                # never delete the sole statement of a body that is a docstring-only; 'pass' keeps syntax valid
                add(node, 'SDL', node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, 'pass')
    return sites


def eligible_files(repo, targets):
    out = []
    for t in targets:
        p = os.path.join(repo, t)
        if os.path.isfile(p):
            out.append(t)
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in sorted(files):
                if f.endswith('.py') and not f.startswith('test_'):
                    out.append(os.path.relpath(os.path.join(root, f), repo))
    return sorted(set(out))


def apply_site(repo, out_dir, site, tree=False, pkg_rel=None):
    """Write the mutated file. tree=True copies the whole pkg_rel dir into out_dir
    first (TransFuser style); else only the mutated file is written at out_dir/<rel>."""
    rel = site['file']
    src = open(os.path.join(repo, rel), encoding='utf-8').read()
    lines = _lines(src)
    l0, c0, l1, c1 = site['span']
    old = _seg(lines, l0, c0, l1, c1)
    assert old == site['old'], f"span mismatch for {site['id']}: {old!r} != {site['old']!r}"
    if l0 == l1:
        lines[l0 - 1] = lines[l0 - 1][:c0] + site['new'] + lines[l0 - 1][c1:]
    else:
        head = lines[l0 - 1][:c0]
        tail = lines[l1 - 1][c1:]
        lines[l0 - 1:l1] = [head + site['new'] + tail]
    new_src = '\n'.join(lines)
    ast.parse(new_src)  # must stay syntactically valid
    if tree:
        assert pkg_rel, 'pkg_rel required with tree=True'
        dst_pkg = os.path.join(out_dir, os.path.basename(pkg_rel))
        if os.path.exists(dst_pkg):
            shutil.rmtree(dst_pkg)
        shutil.copytree(os.path.join(repo, pkg_rel), dst_pkg, ignore=shutil.ignore_patterns('__pycache__'))
        dst = os.path.join(out_dir, os.path.relpath(rel, os.path.dirname(pkg_rel)))
    else:
        dst = os.path.join(out_dir, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(new_src)
    return dst, hashlib.md5(new_src.encode()).hexdigest()


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == 'enumerate':
        repo = a[1]; targets = []; covered = None
        i = 2
        while i < len(a):
            if a[i] == '--covered':
                covered = json.load(open(a[i + 1])); i += 2
            else:
                targets.append(a[i]); i += 1
        out = []
        for rel in eligible_files(repo, targets):
            cov = set(covered.get(rel, [])) if covered is not None else None
            if covered is not None and not cov:
                continue
            out += file_sites(repo, rel, cov)
        json.dump(out, sys.stdout, indent=0)
    elif cmd in ('apply', 'show'):
        repo = a[1]
        if cmd == 'show':
            sid = a[2]
        else:
            out_dir, sid = a[2], a[3]
        rel = sid.split(':')[0]
        sites = {s['id']: s for s in file_sites(repo, rel)}
        s = sites[sid]
        print(json.dumps(s, indent=1))
        if cmd == 'apply':
            tree = '--tree' in a
            pkg = None
            if tree:
                pkg = a[a.index('--tree') + 1]
            dst, md5 = apply_site(repo, out_dir, s, tree=tree, pkg_rel=pkg)
            print('wrote', dst, md5)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
