"""Opt-out keyword detection for STT-based call opt-out.

This module provides keyword detection for the STT opt-out channel.
Called from the voice pipeline after each STT transcription to detect
opt-out intent before forwarding to LLM.

Per D-15, COMP-04: STT keyword opt-out detection must write to consent DB
immediately when triggered.

Usage:
    from holler.core.telecom.optout import check_optout_keywords

    matched = check_optout_keywords("please stop calling me", ["stop", "remove me", "do not call"])
    if matched:
        await consent_db.record_optout(destination, source="stt", call_uuid=call_uuid)
        await esl.hangup(call_uuid)
"""
from __future__ import annotations

from typing import List, Optional


def check_optout_keywords(transcript: str, keywords: List[str]) -> Optional[str]:
    """Check if transcript contains any opt-out keywords.

    Case-insensitive matching. Returns the first matched keyword or None if
    no opt-out keyword is found in the transcript.

    Args:
        transcript: Transcribed text from STT output.
        keywords: List of opt-out keyword strings to check for.
                  Configured via ComplianceConfig.opt_out_keywords.

    Returns:
        The matched keyword string if found (e.g. "stop"), or None if no match.

    Examples:
        >>> check_optout_keywords("please stop calling me", ["stop", "remove me"])
        "stop"
        >>> check_optout_keywords("hello how are you", ["stop", "remove me"])
        None
        >>> check_optout_keywords("Remove Me from your list", ["stop", "remove me"])
        "remove me"
    """
    transcript_lower = transcript.lower()
    for keyword in keywords:
        if keyword.lower() in transcript_lower:
            return keyword
    return None
