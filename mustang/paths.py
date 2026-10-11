"""Where generated files go: deliverables (STLs, the Bambu project, the animation) in output/,
scratch (renders, frames, comparison sheets, probes) in tmp/. Nothing is written to the project root."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "output")
TMP = os.path.join(ROOT, "tmp")
