"""Country compliance modules package.

Each subdirectory is a country module implementing the ComplianceModule ABC
from holler.core.compliance.gateway.

Structure:
    holler/countries/
        us/          # TCPA, DNC, STIR/SHAKEN, time-of-day restrictions
        uk/          # Ofcom rules (community-contributed, v2)
        _template/   # Scaffold for new country modules (D-10)
        contrib/     # Community modules and experiments
"""
