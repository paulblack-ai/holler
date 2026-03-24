"""US jurisdiction compliance module.

Implements TCPA + DNC enforcement for calls to US (+1) destinations.
Registers USComplianceModule as the country-level compliance plugin.

Usage:
    from holler.countries.us import USComplianceModule
    module = USComplianceModule(consent_db=consent_db, dnc_list=dnc_list)
    result = await module.check_outbound("+15550001234", session)
"""
# USComplianceModule is defined in module.py (created in plan 02-04 Task 2)
# Use lazy import to avoid errors when only timezones/tcpa/dnc_check are needed.


def __getattr__(name: str):
    if name == "USComplianceModule":
        from holler.countries.us.module import USComplianceModule  # noqa: PLC0415
        return USComplianceModule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["USComplianceModule"]
