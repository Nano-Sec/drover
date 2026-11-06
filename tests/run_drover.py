#!/usr/bin/env python3
"""Run the helper with a clock that skips its sleeps, so the fast tests stay fast.

The helper file itself is loaded unchanged, then main() runs as it would from the shell.
"""
import importlib.machinery, importlib.util, os, sys, time

path = os.environ["FAKE_DROVER_HELPER"]
skipped = [0.0]
real_time = time.time
time.sleep = lambda seconds: skipped.__setitem__(0, skipped[0] + seconds)
time.time = lambda: real_time() + skipped[0]

loader = importlib.machinery.SourceFileLoader("drover_helper", path)
spec = importlib.util.spec_from_loader("drover_helper", loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)
if os.environ.get("FAKE_JOB_PATIENCE"):
    helper.JOB_PATIENCE = int(os.environ["FAKE_JOB_PATIENCE"])
sys.argv[0] = path
helper.main()
