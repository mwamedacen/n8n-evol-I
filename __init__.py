"""Native Hermes compatibility entrypoint; shared adapter lives in .hermes-plugin."""
from pathlib import Path
import runpy


def register(ctx):
    adapter = Path(__file__).resolve().parent / ".hermes-plugin" / "__init__.py"
    runpy.run_path(str(adapter))["register"](ctx)
