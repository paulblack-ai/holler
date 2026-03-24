"""Telecom abstraction layer package.

Exports TelecomSession (session state) and NumberPool (DID pool management).
"""
from holler.core.telecom.session import TelecomSession

# NumberPool is defined in pool.py (added in Task 2)
# Export it here after pool.py is created
try:
    from holler.core.telecom.pool import NumberPool, NumberPoolExhaustedError
    __all__ = ["TelecomSession", "NumberPool", "NumberPoolExhaustedError"]
except ImportError:
    # pool.py not yet created — allow partial import during Task 1
    __all__ = ["TelecomSession"]
