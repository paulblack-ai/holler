---
phase: quick
plan: 260324-ubt
type: execute
wave: 1
depends_on: []
files_modified:
  - holler/cli/commands.py
  - tests/test_cli.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "holler init downloads Kokoro ONNX model without 404 error"
    - "holler init finds docker-compose.yml when run from pip install (not just source checkout)"
  artifacts:
    - path: "holler/cli/commands.py"
      provides: "Fixed _download_models() and _start_services()"
      contains: "fastrtc/kokoro-onnx"
    - path: "tests/test_cli.py"
      provides: "Test coverage for both fixes"
  key_links:
    - from: "holler/cli/commands.py"
      to: "fastrtc/kokoro-onnx HuggingFace repo"
      via: "hf_hub_download"
      pattern: "hf_hub_download.*fastrtc/kokoro-onnx"
    - from: "holler/cli/commands.py"
      to: "docker/docker-compose.yml"
      via: "_get_project_root with fallback"
      pattern: "_get_project_root|importlib.resources|pkg_resources"
---

<objective>
Fix two bugs in `holler init` CLI command that break the onboarding flow.

Bug 1: Kokoro ONNX model download uses wrong HuggingFace repo (`hexgrad/Kokoro-82M` is the PyTorch repo, does not contain ONNX files). The correct repo is `fastrtc/kokoro-onnx` which has `kokoro-v1.0.onnx` and `voices-v1.0.bin`.

Bug 2: `_get_project_root()` navigates `__file__` -> parent -> parent -> parent, which resolves to the project root in a source checkout but to `site-packages/` (or above) when pip-installed. The fix needs a fallback path resolution strategy.

Purpose: Restore the "four commands to first call" onboarding promise.
Output: Fixed `commands.py` with passing tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@holler/cli/commands.py
@tests/test_cli.py
@holler/core/voice/tts.py
@pyproject.toml

<interfaces>
<!-- TTSConfig expects these exact filenames (from holler/core/voice/tts.py) -->
```python
@dataclass
class TTSConfig:
    model_path: str = "kokoro-v1.0.onnx"    # filename must match download
    voices_path: str = "voices-v1.0.bin"     # filename must match download
```

<!-- Current buggy download code (from holler/cli/commands.py lines 133-141) -->
```python
# BUG: hexgrad/Kokoro-82M is the PyTorch repo (.pth files), not the ONNX repo
hf_hub_download("hexgrad/Kokoro-82M", "kokoro-v1.0.onnx")   # 404!
hf_hub_download("hexgrad/Kokoro-82M", "voices-v1.0.bin")     # 404!
```

<!-- Current buggy path resolution (from holler/cli/commands.py lines 18-24) -->
```python
def _get_project_root() -> Path:
    # Works in source checkout: commands.py -> cli/ -> holler/ -> project_root/
    # FAILS when pip-installed: commands.py -> cli/ -> holler/ -> site-packages/
    return Path(__file__).resolve().parent.parent.parent
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix Kokoro ONNX model download (wrong HuggingFace repo)</name>
  <files>holler/cli/commands.py, tests/test_cli.py</files>
  <behavior>
    - Test 1: _download_models calls hf_hub_download with repo "fastrtc/kokoro-onnx" (not "hexgrad/Kokoro-82M")
    - Test 2: _download_models downloads both "kokoro-v1.0.onnx" and "voices-v1.0.bin" from the correct repo
    - Test 3: _download_models handles download failure gracefully (prints error, does not crash)
  </behavior>
  <action>
In `holler/cli/commands.py`, change the Kokoro ONNX download in `_download_models()` at lines 136-138:

FROM:
```python
hf_hub_download("hexgrad/Kokoro-82M", "kokoro-v1.0.onnx")
hf_hub_download("hexgrad/Kokoro-82M", "voices-v1.0.bin")
```

TO:
```python
hf_hub_download("fastrtc/kokoro-onnx", "kokoro-v1.0.onnx")
hf_hub_download("fastrtc/kokoro-onnx", "voices-v1.0.bin")
```

The filenames are correct (`kokoro-v1.0.onnx`, `voices-v1.0.bin`) -- only the repo ID is wrong. The `fastrtc/kokoro-onnx` HuggingFace repo contains exactly these two files (confirmed: 326 MB ONNX model + 28.2 MB voice data).

In `tests/test_cli.py`, add a new test class `TestDownloadModels` with tests that mock `hf_hub_download` and `WhisperModel` to verify:
- The correct HF repo ID is used (`fastrtc/kokoro-onnx`)
- Both filenames are downloaded
- Failure in one download doesn't prevent the other from attempting
  </action>
  <verify>
    <automated>cd /Users/paul/paul/Projects/holler && python -m pytest tests/test_cli.py::TestDownloadModels -xvs 2>&1 | tail -20</automated>
  </verify>
  <done>hf_hub_download calls use "fastrtc/kokoro-onnx" repo ID; tests confirm correct repo and filenames</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fix Docker Compose path resolution for pip-installed package</name>
  <files>holler/cli/commands.py, tests/test_cli.py</files>
  <behavior>
    - Test 1: _get_project_root returns a path containing docker/docker-compose.yml when run from source checkout (current behavior, preserved)
    - Test 2: _start_services falls back to CWD-based docker/ lookup when __file__-based path has no docker-compose.yml (simulates pip install)
    - Test 3: _start_services prints helpful error when docker-compose.yml not found at either location
  </behavior>
  <action>
Modify `_start_services()` in `holler/cli/commands.py` to add a fallback path resolution strategy. The current `_get_project_root()` approach works for source checkouts. When pip-installed, the three-parent traversal lands in `site-packages/` which has no `docker/` directory.

Strategy: Keep `_get_project_root()` as the primary attempt (backward compatible for source checkouts). Add fallback that checks `Path.cwd() / "docker" / "docker-compose.yml"`. This handles the common case where the user cloned the repo and ran `pip install -e .` or is running from the project directory.

Update `_start_services()` to:

```python
def _start_services():
    """Start Docker Compose services and wait for health."""
    click.echo("  Starting Docker Compose services...")

    # Primary: resolve from package location (works in source checkout / editable install)
    project_root = _get_project_root()
    compose_file = project_root / "docker" / "docker-compose.yml"

    # Fallback: check CWD (works when user is in project dir with pip install)
    if not compose_file.exists():
        compose_file = Path.cwd() / "docker" / "docker-compose.yml"

    if not compose_file.exists():
        click.secho(
            "  docker-compose.yml not found. Run from the holler project directory,\n"
            "  or set HOLLER_COMPOSE_FILE to the path of your docker-compose.yml.",
            fg="red",
        )
        return

    # Also check HOLLER_COMPOSE_FILE env var as an explicit override
    env_compose = os.environ.get("HOLLER_COMPOSE_FILE")
    if env_compose:
        compose_file = Path(env_compose)
        if not compose_file.exists():
            click.secho(f"  HOLLER_COMPOSE_FILE={env_compose} not found", fg="red")
            return

    # ... rest of subprocess.run unchanged, but use compose_file.parent for --project-directory
```

Update `--project-directory` to use `str(compose_file.parent)` instead of `str(project_root / "docker")` so it's consistent with whichever path was resolved.

In `tests/test_cli.py`, update `TestStartServices`:
- Keep `test_get_project_root_contains_docker_compose` (still valid for source checkout)
- Add `test_start_services_falls_back_to_cwd` that mocks `_get_project_root` to return a bogus path and verifies CWD fallback
- Add `test_start_services_respects_env_var_override` that sets HOLLER_COMPOSE_FILE and verifies it's used
- Add `test_start_services_helpful_error_when_not_found` that verifies the error message when neither path works
  </action>
  <verify>
    <automated>cd /Users/paul/paul/Projects/holler && python -m pytest tests/test_cli.py::TestStartServices -xvs 2>&1 | tail -30</automated>
  </verify>
  <done>_start_services resolves docker-compose.yml via __file__-based path, CWD fallback, or HOLLER_COMPOSE_FILE env var; error message is helpful when none found; all tests pass</done>
</task>

</tasks>

<verification>
```bash
# Run all CLI tests to ensure no regressions
cd /Users/paul/paul/Projects/holler && python -m pytest tests/test_cli.py -xvs

# Verify the correct HF repo is referenced (not the old one)
grep -n "hexgrad/Kokoro-82M" holler/cli/commands.py  # Should return nothing
grep -n "fastrtc/kokoro-onnx" holler/cli/commands.py  # Should show the download lines

# Verify fallback path logic exists
grep -n "HOLLER_COMPOSE_FILE\|cwd\|fallback" holler/cli/commands.py
```
</verification>

<success_criteria>
- `python -m pytest tests/test_cli.py -xvs` passes all tests (existing + new)
- `grep "hexgrad/Kokoro-82M" holler/cli/commands.py` returns no matches (old repo removed)
- `grep "fastrtc/kokoro-onnx" holler/cli/commands.py` returns matches (correct repo used)
- _start_services has fallback path resolution (not just __file__-based)
- Error message when docker-compose.yml not found is actionable
</success_criteria>

<output>
After completion, create `.planning/quick/260324-ubt-fix-holler-init-kokoro-onnx-model-downlo/260324-ubt-SUMMARY.md`
</output>
