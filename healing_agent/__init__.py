from .healing_agent import healing_agent as _healing_agent

# Make the module callable by implementing __call__
class HealingAgentModule:
    def __init__(self):
        self.healing_agent = _healing_agent
    
    def __call__(self, *args, **kwargs):
        return self.healing_agent(*args, **kwargs)

# Replace the module with our callable instance
import sys
sys.modules[__name__] = HealingAgentModule()

__all__ = ['healing_agent']
