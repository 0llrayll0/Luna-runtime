from __future__ import annotations

from luna.api.app import create_app
from luna.runtime.core import LunaRuntime

runtime = LunaRuntime()
app = create_app(runtime)

__all__ = ["app", "runtime"]