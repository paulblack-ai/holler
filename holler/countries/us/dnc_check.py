"""DNC (Do Not Call) list compliance check for US outbound calls.

Wraps the DNCList data layer to produce a ComplianceResult. Per D-12 and COMP-03.

The DNC check runs FIRST in the US compliance module check order because it is
the cheapest operation (single SQLite PRIMARY KEY lookup) and catches the most
clear-cut denials before any other work is done.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from holler.core.compliance.gateway import ComplianceResult

if TYPE_CHECKING:
    from holler.core.compliance.dnc import DNCList


async def check_dnc(
    destination: str,
    dnc_list: "DNCList",
) -> ComplianceResult:
    """Check whether the destination number is on the operator DNC list.

    Uses a single PRIMARY KEY lookup against the SQLite DNC table. O(1) by index.

    Per D-12: The DNC list is operator-managed (imported from FTC registry or
    custom list). This check does not contact any external service.

    Args:
        destination: E.164 destination phone number (e.g. "+12125551234").
        dnc_list: Initialized DNCList instance.

    Returns:
        ComplianceResult with check_type="dnc".
        - passed=False, reason="dnc_listed" if number is on DNC list.
        - passed=True, reason="not_on_dnc" if number is not on DNC list.
    """
    on_dnc = await dnc_list.is_on_dnc(destination)

    if on_dnc:
        return ComplianceResult(
            passed=False,
            reason="dnc_listed",
            check_type="dnc",
            audit_fields={
                "destination": destination,
                "check": "dnc",
                "dnc_match": True,
            },
        )

    return ComplianceResult(
        passed=True,
        reason="not_on_dnc",
        check_type="dnc",
        audit_fields={
            "destination": destination,
            "check": "dnc",
            "dnc_match": False,
        },
    )
