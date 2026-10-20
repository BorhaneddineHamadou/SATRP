"""openpilot mutant import hook.

Activated by the venv .pth file (a2_op_mutant.pth) in EVERY interpreter of
~/openpilot/.venv when env OP_MUTANT_FILE is set, so the manager and all the
daemons it spawns (controlsd, plannerd, radard, modeld, ...) see the mutant.

  OP_MUTANT_FILE = "<dotted.module.name>=<absolute path to mutated .py>"
                   (';'-separated for several modules)
  OP_MUTANT_LOG  = file to append "pid module path md5" lines (verification)

The finder redirects ONLY the named module(s); everything else loads normally.
"""
import hashlib
import importlib.abc
import importlib.util
import os
import sys


class _MutantFinder(importlib.abc.MetaPathFinder):
    def __init__(self, mapping):
        self.mapping = mapping

    def find_spec(self, fullname, path=None, target=None):
        p = self.mapping.get(fullname)
        if p is None:
            return None
        spec = importlib.util.spec_from_file_location(fullname, p)
        try:
            log = os.environ.get("OP_MUTANT_LOG")
            if log:
                with open(p, "rb") as f:
                    md5 = hashlib.md5(f.read()).hexdigest()
                with open(log, "a") as f:
                    f.write(f"{os.getpid()} {fullname} {p} {md5}\n")
        except Exception:
            pass
        return spec


def install():
    raw = os.environ.get("OP_MUTANT_FILE", "")
    mapping = {}
    for item in raw.split(";"):
        if "=" in item:
            mod, p = item.split("=", 1)
            mapping[mod.strip()] = p.strip()
    if mapping and not any(isinstance(f, _MutantFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _MutantFinder(mapping))


install()
