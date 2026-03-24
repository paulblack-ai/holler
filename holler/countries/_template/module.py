"""Country module template — scaffold for new jurisdiction compliance modules.

HOW TO USE THIS TEMPLATE
=========================

1. Copy this directory to holler/countries/{country_code}/
   Example: cp -r holler/countries/_template holler/countries/au

2. Rename TemplateComplianceModule to {Country}ComplianceModule
   Example: AustraliaComplianceModule

3. Update the E.164 prefix in the registration example below
   Example: "+61" for Australia

4. Implement each check in check_outbound() replacing the NotImplementedError
   placeholders with your jurisdiction's rules.

5. Register your module in your application startup:
   from holler.core.telecom.router import JurisdictionRouter
   from holler.countries.au.module import AustraliaComplianceModule
   router.register("+61", AustraliaComplianceModule())

6. Submit a PR to the holler repo so others can use your module.

CONTRACT
========

Every country module MUST:
- Subclass ComplianceModule (this ABC is the only contract)
- Implement check_outbound(destination, session) -> ComplianceResult
- Return ComplianceResult(passed=True, ...) to allow the call
- Return ComplianceResult(passed=False, ...) to deny the call
- NEVER raise exceptions — catch all errors and return a deny result
  (the gateway handles exceptions, but fail-closed is better than raising)
- NEVER block for more than 2 seconds (default gateway timeout)

The gateway guarantees:
- check_outbound() is always called before esl.originate()
- If check_outbound() raises, the call is blocked (fail-closed)
- If check_outbound() times out, the call is blocked (fail-closed)
- Every result (pass or fail) is written to the audit log

TYPICAL CHECKS TO IMPLEMENT
============================

1. Consent verification
   - Does the caller have prior express consent from this number?
   - Query your consent database by destination number.
   - If no consent record: return deny with reason="no_consent"

2. Do Not Call (DNC) list check
   - Is the destination number on a national/state DNC list?
   - Query your local DNC database (SQLite or in-memory set).
   - If on DNC list: return deny with reason="dnc_match"

3. Time-of-day restrictions
   - Is the current time within allowed calling hours for this jurisdiction?
   - Derive recipient timezone from area code / country code.
   - If outside allowed hours: return deny with reason="time_of_day"

4. Caller identification
   - Does the caller have a valid Caller ID / CLI for this jurisdiction?
   - Verify the DID is registered and valid.
   - If CLI spoofing rules apply: check STIR/SHAKEN attestation level.

5. Jurisdiction-specific rules
   - Any country-specific requirements (e.g., OFCOM rules for UK,
     ACMA rules for Australia, CRTC rules for Canada).

EXAMPLE IMPLEMENTATIONS
=======================

See holler/countries/us/module.py for a complete US (TCPA) implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from holler.core.compliance.gateway import ComplianceModule, ComplianceResult

if TYPE_CHECKING:
    from holler.core.telecom.session import TelecomSession


class TemplateComplianceModule(ComplianceModule):
    """Template compliance module — replace this docstring with your jurisdiction.

    This module returns ComplianceResult(passed=False, reason="template_not_implemented")
    for all calls. This is intentional fail-closed behavior — a template that has not
    been implemented should NEVER allow calls through.

    Rename this class to {Country}ComplianceModule before using in production.

    Example registration:
        from holler.core.telecom.router import JurisdictionRouter
        from holler.countries._template.module import TemplateComplianceModule

        router = JurisdictionRouter()
        router.register("+XX", TemplateComplianceModule())
        # Replace "+XX" with your country's E.164 prefix (e.g., "+61" for Australia)
    """

    async def check_outbound(
        self,
        destination: str,
        session: "TelecomSession",
    ) -> ComplianceResult:
        """Check whether an outbound call to `destination` is permitted.

        REPLACE THIS IMPLEMENTATION with your jurisdiction's compliance rules.
        The current implementation denies all calls with "template_not_implemented".

        Implementation guide:
        --------------------
        1. Check consent (see TYPICAL CHECKS section above)
        2. Check DNC list
        3. Check time-of-day restrictions
        4. Check caller identification / CLI requirements
        5. Run any jurisdiction-specific checks

        Each check should return a ComplianceResult immediately if it fails:

            consent = await self._check_consent(destination, session)
            if not consent:
                return ComplianceResult(
                    passed=False,
                    reason="no_consent",
                    check_type="consent",
                    audit_fields={"destination": destination},
                )

        If all checks pass, return:

            return ComplianceResult(
                passed=True,
                reason="all_checks_passed",
                check_type="full",
                audit_fields={"checks_run": ["consent", "dnc", "time_of_day"]},
            )

        Args:
            destination: E.164 destination phone number (e.g. "+61299123456").
            session: TelecomSession with DID, jurisdiction, consent state, etc.

        Returns:
            ComplianceResult with passed=True (allow) or passed=False (deny).
            Include a descriptive reason and relevant audit_fields.
        """
        # TODO: Replace this placeholder with your jurisdiction's checks.
        #
        # This default denies all calls — fail-closed until implemented.
        # A template that passes calls without checking would be a safety hazard.
        return ComplianceResult(
            passed=False,
            reason="template_not_implemented",
            check_type="template",
            audit_fields={
                "note": (
                    "This is the template module. Copy holler/countries/_template/ "
                    "to holler/countries/{country_code}/ and implement check_outbound()."
                ),
                "destination": destination,
            },
        )
