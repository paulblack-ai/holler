"""Telecom abstraction layer package.

Exports TelecomSession (session state) and NumberPool (DID pool management).
"""
from holler.core.telecom.session import TelecomSession
from holler.core.telecom.pool import NumberPool, NumberPoolExhaustedError

__all__ = ["TelecomSession", "NumberPool", "NumberPoolExhaustedError"]
