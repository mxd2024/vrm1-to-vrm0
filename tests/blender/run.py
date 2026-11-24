"""Blender の中で tests/blender/test_*.py を走らせる。

blender -b --python-exit-code 1 --python tests/blender/run.py -- <pattern>
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
pattern = argv[0] if argv else "test_*.py"
if not pattern.endswith(".py"):
    pattern += ".py"

suite = unittest.defaultTestLoader.discover(
    os.path.join(ROOT, "tests", "blender"), pattern=pattern, top_level_dir=ROOT
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or result.testsRun == 0:
    sys.exit(1)
