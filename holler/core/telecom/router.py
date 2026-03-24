"""JurisdictionRouter — maps E.164 destination prefix to compliance module.

The router is the bridge between a phone number and the country module that
governs it. It uses longest-prefix-match so that "+1415" (San Francisco)
can override "+1" (all US) when needed.

Fail-closed: unknown destinations are denied, not allowed. Per D-09.
"""
from __future__ import annotations

from typing import Dict

from holler.core.compliance.gateway import ComplianceModule, NoComplianceModuleError


class JurisdictionRouter:
    """Maps E.164 destination prefix to compliance module. Fail-closed on unknown.

    Usage:
        router = JurisdictionRouter()
        router.register("+1", USComplianceModule())
        router.register("+44", UKComplianceModule())

        module = router.resolve("+14155551234")  # Returns USComplianceModule
        module = router.resolve("+447911123456")  # Returns UKComplianceModule
        module = router.resolve("+8613800138000")  # Raises NoComplianceModuleError

    Longest-prefix-match means "+1415" takes priority over "+1" for San
    Francisco numbers — useful for sub-jurisdiction overrides.

    Per D-08: jurisdiction router calls the correct module based on E.164 prefix.
    Per D-09: if no module exists for a destination, the call is denied by default.
    """

    def __init__(self) -> None:
        self._modules: Dict[str, ComplianceModule] = {}

    def register(self, prefix: str, module: ComplianceModule) -> None:
        """Register a compliance module for an E.164 prefix.

        Args:
            prefix: E.164 country or sub-country prefix (e.g. "+1", "+44", "+1415").
                    Must start with "+".
            module: ComplianceModule instance to handle calls to this prefix.
        """
        self._modules[prefix] = module

    def resolve(self, destination: str) -> ComplianceModule:
        """Map destination to compliance module. Longest prefix match wins.

        Iterates registered prefixes in descending length order, returning the
        first one that matches the destination string. This guarantees that a
        more specific prefix ("+1415") beats a broader one ("+1").

        Args:
            destination: E.164 destination phone number (e.g. "+14155551234").

        Returns:
            The ComplianceModule registered for the best-matching prefix.

        Raises:
            NoComplianceModuleError: If no registered prefix matches the
                destination (fail-closed — unknown destinations are denied).
        """
        # Sort prefixes by length descending for longest-match-first
        for prefix in sorted(self._modules.keys(), key=len, reverse=True):
            if destination.startswith(prefix):
                return self._modules[prefix]

        raise NoComplianceModuleError(
            f"No compliance module for destination {destination[:4]}... - call denied"
        )

    def list_jurisdictions(self) -> Dict[str, str]:
        """Return registered prefix to module class name mapping.

        Useful for diagnostics and operator tooling — shows which jurisdictions
        are currently configured.

        Returns:
            Dict mapping E.164 prefix to module class name (e.g. {"+ 1": "USComplianceModule"}).
        """
        return {
            prefix: type(module).__name__
            for prefix, module in self._modules.items()
        }
