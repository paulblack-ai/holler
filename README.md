# holler

Open-source voice and text infrastructure for AI agents. Permissionless core. Community-built country modules.

> You don't need permission to holler.

## What this is

Holler gives AI agents a mouth and an ear. It's a self-hosted telecom stack that lets autonomous agents make phone calls, send texts, and hold voice conversations — using hardware you own, with no vendor accounts and no human in the loop.

The phone network was built for humans. Holler is a bridge from that infrastructure into whatever comes next.

## Quick start

```bash
pip install holler
holler init
holler trunk add --provider voipms --user xxx --pass xxx
holler call +44XXXXXXXXXX --agent "Say hello and ask how their day is going."
```

Four commands. No dashboard. No account creation. No OAuth flow.

## How it works

| Layer | What | How |
|---|---|---|
| Agent interface | LLM emits tool calls (`call`, `sms`, `transfer`) | Python SDK / CLI |
| Voice pipeline | Local STT + TTS, real-time streaming | faster-whisper + Piper/Kokoro |
| Compliance | Per-country plugins in the call path | Community-contributed modules |
| Routing | FreeSWITCH softswitch | Self-hosted, open source |
| Transport | SIP trunk / GSM modem / WebRTC mesh | Your choice of on-ramp |

## Country modules

The core is jurisdiction-agnostic. Compliance lives in country modules — community-contributed plugins that enforce local rules.

```bash
holler module add us    # Activates TCPA, STIR/SHAKEN, DNC, state overlays
holler module add uk    # Activates Ofcom/TPS rules
```

No module for your country? [Build one.](docs/contributing-country-modules.md) You know your local telecom rules better than anyone.

## The bridge

This project might be obsolete in three years. Carriers might build agent-native interfaces. Something new might replace phone numbers entirely. That's fine. Holler is designed to be useful *now* — a bridge from the infrastructure that exists to whatever comes next. If it accelerates that transition, it did its job.

## Contributing

The highest-impact contribution is a country module for your jurisdiction. Start with a markdown file documenting the rules — the code comes later. Understanding your country's telecom regulations is the hard part. Turning that into a compliance gateway is the easy part.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

Apache 2.0. Fork it. Build on it. Make it yours.
