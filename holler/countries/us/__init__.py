"""US jurisdiction compliance module.

Implements TCPA + DNC enforcement for calls to US (+1) destinations.
Registers USComplianceModule as the country-level compliance plugin.

Usage:
    from holler.countries.us import USComplianceModule
    module = USComplianceModule(consent_db=consent_db, dnc_list=dnc_list)
    result = await module.check_outbound("+15550001234", session)
"""
from holler.countries.us.module import USComplianceModule

__all__ = ["USComplianceModule"]
