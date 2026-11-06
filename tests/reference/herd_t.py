#!/usr/bin/env python3
"""Run the private helper unmodified, with its registry redirected to REG_OVERRIDE."""
import importlib.machinery, importlib.util, os, sys
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "b", "herd")
l = importlib.machinery.SourceFileLoader("herd_mod", src)
spec = importlib.util.spec_from_loader("herd_mod", l)
h = importlib.util.module_from_spec(spec); l.exec_module(h)
h.REG_PATH = os.environ["REG_OVERRIDE"]
h.load.__defaults__ = (h.REG_PATH,)
h.save.__defaults__ = (h.REG_PATH,)
sys.argv[0] = "herd"
h.main()
