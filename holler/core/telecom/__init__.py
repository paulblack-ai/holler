"""Telecom abstraction layer package.

Exports TelecomSession (session state), NumberPool (DID pool management),
and check_optout_keywords (STT keyword opt-out detection).
"""
from holler.core.telecom.session import TelecomSession
from holler.core.telecom.pool import NumberPool, NumberPoolExhaustedError
from holler.core.telecom.router import JurisdictionRouter
from holler.core.telecom.optout import check_optout_keywords

__all__ = [
    "TelecomSession",
    "NumberPool",
    "NumberPoolExhaustedError",
    "JurisdictionRouter",
    "check_optout_keywords",
]
