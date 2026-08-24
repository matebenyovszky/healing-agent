from ._version import CONFIG_SCHEMA_VERSION, __version__
from .capture import capture as _capture
from .healing_agent import healing_agent as _healing_agent
from .request import HealingRequested as _HealingRequested
from .request import request_healing as _request_healing
from .log_buffer import disable_log_capture as _disable_log_capture
from .log_buffer import enable_log_capture as _enable_log_capture

_PUBLIC = [
    'healing_agent',
    'request_healing',
    'HealingRequested',
    'capture',
    'enable_log_capture',
    'disable_log_capture',
    '__version__',
    'CONFIG_SCHEMA_VERSION',
]


# Make the module callable by implementing __call__
class HealingAgentModule:
    def __init__(self):
        self.healing_agent = _healing_agent
        # Observation entry points: evidence without a failure, and the
        # optional ring buffer of the application's own log records.
        # Ask for a repair from a handled error branch, not only by raising.
        self.request_healing = _request_healing
        self.HealingRequested = _HealingRequested
        self.capture = _capture
        self.enable_log_capture = _enable_log_capture
        self.disable_log_capture = _disable_log_capture
        # The module object is replaced by this instance below, so anything a
        # caller expects to read off `healing_agent` must be set here.
        self.__version__ = __version__
        self.CONFIG_SCHEMA_VERSION = CONFIG_SCHEMA_VERSION
        self.__name__ = 'healing_agent'
        self.__all__ = list(_PUBLIC)
        # Keep the package attributes the import system needs. Without
        # __path__ the instance is not recognised as a package, and any
        # submodule not already imported by this file becomes unimportable
        # (`import healing_agent.config_template` used to fail).
        self.__path__ = __path__
        self.__file__ = __file__
        self.__spec__ = __spec__
        self.__loader__ = __loader__

    def __call__(self, *args, **kwargs):
        return self.healing_agent(*args, **kwargs)

# Replace the module with our callable instance
import sys
sys.modules[__name__] = HealingAgentModule()

__all__ = list(_PUBLIC)
