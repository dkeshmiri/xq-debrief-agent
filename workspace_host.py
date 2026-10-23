"""Mount isolated applications from one implementation, without changing process environment."""
import importlib.util
from pathlib import Path
from threading import Lock
from uuid import uuid4
import sys


def load_workspace(experience='business', data_root=None):
    name = f'xq_{experience}_{uuid4().hex}'
    source = Path(__file__).resolve().parent / 'app.py'
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    module.WORKSPACE_EXPERIENCE = experience
    module.WORKSPACE_DATA_ROOT = data_root
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        if hasattr(module, 'background_stop'):
            module.background_stop.set()
        if hasattr(module, 'voice_pipeline'):
            module.voice_pipeline.stop()
        raise
    return module


class LazyBusinessApplication:
    """Initialize once on first /business request; no business work at family startup."""
    def __init__(self, data_root=None):
        self.data_root = data_root
        self.module = None
        self.lock = Lock()

    def __call__(self, environ, start_response):
        if self.module is None:
            with self.lock:
                if self.module is None:
                    self.module = load_workspace(data_root=self.data_root)
        return self.module.app(environ, start_response)
