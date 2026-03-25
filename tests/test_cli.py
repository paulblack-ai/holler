"""Tests for holler CLI commands and configuration loading.

Tests CLI command structure, trunk config writing, env file generation,
and HollerConfig SMS field loading.
"""
import os
import unittest.mock as mock
from pathlib import Path

import pytest
from click.testing import CliRunner

from holler.cli.commands import (
    cli,
    _generate_env_file,
    _write_trunk_config,
    _get_project_root,
)


class TestCLICommandStructure:
    """CLI group contains expected subcommands."""

    def test_cli_group_has_init_command(self):
        assert "init" in cli.commands

    def test_cli_group_has_trunk_command(self):
        assert "trunk" in cli.commands

    def test_cli_group_has_call_command(self):
        assert "call" in cli.commands

    def test_cli_group_command_count(self):
        # init, trunk, call (at minimum)
        assert len(cli.commands) >= 3

    def test_cli_help_text(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "holler" in result.output.lower() or "voice" in result.output.lower()


class TestTrunkCommand:
    """trunk command accepts --password and --pass flags (per D-15)."""

    def test_trunk_accepts_password_flag(self):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["trunk", "--host", "sip.example.com", "--user", "testuser", "--password", "secret"],
        )
        assert result.exit_code == 0
        assert "sip.example.com" in result.output

    def test_trunk_accepts_pass_flag(self):
        """--pass alias must work (per D-15)."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["trunk", "--host", "sip.example.com", "--user", "testuser", "--pass", "secret"],
        )
        assert result.exit_code == 0
        assert "sip.example.com" in result.output

    def test_trunk_success_message_contains_host_and_user(self):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["trunk", "--host", "sip.carrier.io", "--user", "myagent", "--password", "abc123"],
        )
        assert result.exit_code == 0
        assert "myagent@sip.carrier.io" in result.output


class TestGenerateEnvFile:
    """_generate_env_file() creates .holler.env with expected keys."""

    def test_creates_env_file(self, tmp_path):
        env_file = tmp_path / ".holler.env"
        with mock.patch("holler.cli.commands.os.path.exists", return_value=False), \
             mock.patch("builtins.open", mock.mock_open()) as mock_file, \
             mock.patch("holler.cli.commands.click.echo"):
            _generate_env_file()
            mock_file.assert_called()

    def test_env_file_contains_esl_host(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands.click.echo"):
                _generate_env_file()
            content = env_path.read_text()
            assert "ESL_HOST=127.0.0.1" in content
        finally:
            os.chdir(orig_cwd)

    def test_env_file_contains_whisper_model(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands.click.echo"):
                _generate_env_file()
            content = env_path.read_text()
            assert "WHISPER_MODEL=distil-large-v3" in content
        finally:
            os.chdir(orig_cwd)

    def test_env_file_contains_smsc_host(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands.click.echo"):
                _generate_env_file()
            content = env_path.read_text()
            assert "HOLLER_SMSC_HOST=127.0.0.1" in content
        finally:
            os.chdir(orig_cwd)

    def test_env_file_contains_redis_url(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands.click.echo"):
                _generate_env_file()
            content = env_path.read_text()
            assert "HOLLER_REDIS_URL=redis://localhost:6379" in content
        finally:
            os.chdir(orig_cwd)

    def test_skips_if_file_exists(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        env_path.write_text("EXISTING=true\n")
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands.click.echo") as mock_echo:
                _generate_env_file()
            # File should be unchanged (not overwritten)
            assert env_path.read_text() == "EXISTING=true\n"
            # Should print "already exists" message
            calls = " ".join(str(c) for c in mock_echo.call_args_list)
            assert "already exists" in calls
        finally:
            os.chdir(orig_cwd)


class TestWriteTrunkConfig:
    """_write_trunk_config() updates or appends trunk vars to .holler.env."""

    def test_writes_trunk_vars_to_new_file(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            _write_trunk_config("sip.example.com", "alice", "hunter2")
            content = env_path.read_text()
            assert "HOLLER_TRUNK_HOST=sip.example.com" in content
            assert "HOLLER_TRUNK_USER=alice" in content
            assert "HOLLER_TRUNK_PASS=hunter2" in content
        finally:
            os.chdir(orig_cwd)

    def test_updates_existing_trunk_host_line(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        env_path.write_text(
            "ESL_HOST=127.0.0.1\n"
            "HOLLER_TRUNK_HOST=old.sip.host\n"
            "HOLLER_TRUNK_USER=olduser\n"
            "HOLLER_TRUNK_PASS=oldpass\n"
        )
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            _write_trunk_config("new.sip.host", "newuser", "newpass")
            content = env_path.read_text()
            assert "HOLLER_TRUNK_HOST=new.sip.host" in content
            assert "old.sip.host" not in content
            assert "HOLLER_TRUNK_USER=newuser" in content
            assert "HOLLER_TRUNK_PASS=newpass" in content
            # Unrelated key preserved
            assert "ESL_HOST=127.0.0.1" in content
        finally:
            os.chdir(orig_cwd)

    def test_appends_trunk_vars_if_no_trunk_section(self, tmp_path):
        env_path = tmp_path / ".holler.env"
        env_path.write_text("ESL_HOST=127.0.0.1\nWHISPER_MODEL=distil-large-v3\n")
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            _write_trunk_config("sip.carrier.io", "agent", "p4ssw0rd")
            content = env_path.read_text()
            assert "HOLLER_TRUNK_HOST=sip.carrier.io" in content
            assert "HOLLER_TRUNK_USER=agent" in content
            assert "HOLLER_TRUNK_PASS=p4ssw0rd" in content
            # Pre-existing content still there
            assert "ESL_HOST=127.0.0.1" in content
            assert "WHISPER_MODEL=distil-large-v3" in content
        finally:
            os.chdir(orig_cwd)


class TestDownloadModels:
    """_download_models() uses correct HuggingFace repo for Kokoro ONNX."""

    def _make_import_mock(self, mock_hf_download):
        """Return a side_effect function for __import__ that intercepts huggingface_hub and faster_whisper."""
        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def fake_import(name, *args, **kwargs):
            if name == "huggingface_hub":
                m = mock.MagicMock()
                m.hf_hub_download = mock_hf_download
                return m
            if name == "faster_whisper":
                m = mock.MagicMock()
                return m
            return real_import(name, *args, **kwargs)

        return fake_import

    def test_download_models_uses_fastrtc_kokoro_onnx_repo(self):
        """hf_hub_download must be called with 'fastrtc/kokoro-onnx', not 'hexgrad/Kokoro-82M'."""
        from holler.cli.commands import _download_models
        mock_hf = mock.MagicMock()
        with mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho"), \
             mock.patch("builtins.__import__", side_effect=self._make_import_mock(mock_hf)):
            _download_models()
        calls = mock_hf.call_args_list
        repos = [call[0][0] for call in calls]
        assert "fastrtc/kokoro-onnx" in repos, (
            f"Expected 'fastrtc/kokoro-onnx' repo but got: {repos}"
        )
        assert "hexgrad/Kokoro-82M" not in repos, (
            f"Old wrong repo 'hexgrad/Kokoro-82M' should not be used, but found in: {repos}"
        )

    def test_download_models_downloads_both_kokoro_files(self):
        """Both kokoro-v1.0.onnx and voices-v1.0.bin must be downloaded from fastrtc/kokoro-onnx."""
        from holler.cli.commands import _download_models
        mock_hf = mock.MagicMock()
        with mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho"), \
             mock.patch("builtins.__import__", side_effect=self._make_import_mock(mock_hf)):
            _download_models()
        # Collect (repo, filename) pairs from Kokoro calls
        kokoro_calls = [
            (call[0][0], call[0][1])
            for call in mock_hf.call_args_list
            if len(call[0]) >= 2
        ]
        assert ("fastrtc/kokoro-onnx", "kokoro-v1.0.onnx") in kokoro_calls, (
            f"Expected (fastrtc/kokoro-onnx, kokoro-v1.0.onnx) in calls: {kokoro_calls}"
        )
        assert ("fastrtc/kokoro-onnx", "voices-v1.0.bin") in kokoro_calls, (
            f"Expected (fastrtc/kokoro-onnx, voices-v1.0.bin) in calls: {kokoro_calls}"
        )

    def test_download_models_handles_failure_gracefully(self):
        """If hf_hub_download raises, _download_models prints error and does not crash."""
        from holler.cli.commands import _download_models
        mock_hf_fail = mock.MagicMock(side_effect=Exception("Network error"))
        with mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho") as mock_secho, \
             mock.patch("builtins.__import__", side_effect=self._make_import_mock(mock_hf_fail)):
            # Must not raise
            _download_models()
        # Should have printed an error via click.secho with fg="red"
        red_calls = [
            c for c in mock_secho.call_args_list
            if c[1].get("fg") == "red" or (len(c[0]) > 0 and "failed" in str(c[0][0]))
        ]
        assert len(red_calls) > 0, "Expected at least one error message printed on failure"


class TestStartServices:
    """_start_services() resolves compose file path from package location."""

    def test_get_project_root_contains_docker_compose(self):
        from holler.cli.commands import _get_project_root
        root = _get_project_root()
        assert (root / "docker" / "docker-compose.yml").exists()

    def test_start_services_passes_compose_file_flag(self):
        with mock.patch("holler.cli.commands.subprocess.run") as mock_run, \
             mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho"):
            mock_run.return_value = mock.Mock(returncode=0)
            from holler.cli.commands import _start_services
            # Mock socket to avoid waiting for FreeSWITCH
            with mock.patch("socket.socket"):
                _start_services()
            args = mock_run.call_args[0][0]
            assert "-f" in args
            compose_idx = args.index("-f") + 1
            assert args[compose_idx].endswith("docker/docker-compose.yml")

    def test_start_services_passes_project_directory_flag(self):
        with mock.patch("holler.cli.commands.subprocess.run") as mock_run, \
             mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho"):
            mock_run.return_value = mock.Mock(returncode=0)
            from holler.cli.commands import _start_services
            with mock.patch("socket.socket"):
                _start_services()
            args = mock_run.call_args[0][0]
            assert "--project-directory" in args

    def test_start_services_falls_back_to_cwd(self, tmp_path):
        """When __file__-based path has no docker-compose.yml, fall back to CWD/docker/."""
        from holler.cli.commands import _start_services
        # Create docker/docker-compose.yml in tmp_path (simulates CWD)
        docker_dir = tmp_path / "docker"
        docker_dir.mkdir()
        (docker_dir / "docker-compose.yml").write_text("version: '3'\n")
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with mock.patch("holler.cli.commands._get_project_root",
                            return_value=Path("/nonexistent/bogus/path")), \
                 mock.patch("holler.cli.commands.subprocess.run") as mock_run, \
                 mock.patch("holler.cli.commands.click.echo"), \
                 mock.patch("holler.cli.commands.click.secho"), \
                 mock.patch("socket.socket"):
                mock_run.return_value = mock.Mock(returncode=0)
                _start_services()
            # subprocess.run must have been called (not early-returned due to missing file)
            assert mock_run.called, "subprocess.run should be called when CWD fallback resolves"
            args = mock_run.call_args[0][0]
            compose_idx = args.index("-f") + 1
            assert "docker-compose.yml" in args[compose_idx]
        finally:
            os.chdir(orig_cwd)

    def test_start_services_respects_env_var_override(self, tmp_path):
        """HOLLER_COMPOSE_FILE env var overrides all path resolution."""
        from holler.cli.commands import _start_services
        # Create a compose file at a custom path
        custom_compose = tmp_path / "custom-compose.yml"
        custom_compose.write_text("version: '3'\n")
        with mock.patch.dict(os.environ, {"HOLLER_COMPOSE_FILE": str(custom_compose)}), \
             mock.patch("holler.cli.commands.subprocess.run") as mock_run, \
             mock.patch("holler.cli.commands.click.echo"), \
             mock.patch("holler.cli.commands.click.secho"), \
             mock.patch("socket.socket"):
            mock_run.return_value = mock.Mock(returncode=0)
            _start_services()
        assert mock_run.called, "subprocess.run should be called when HOLLER_COMPOSE_FILE is set"
        args = mock_run.call_args[0][0]
        compose_idx = args.index("-f") + 1
        assert args[compose_idx] == str(custom_compose)

    def test_start_services_helpful_error_when_not_found(self, tmp_path):
        """Prints actionable error when docker-compose.yml not found at any path."""
        from holler.cli.commands import _start_services
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)  # CWD has no docker/ directory
        try:
            with mock.patch("holler.cli.commands._get_project_root",
                            return_value=Path("/nonexistent/bogus/path")), \
                 mock.patch.dict(os.environ, {}, clear=False), \
                 mock.patch("holler.cli.commands.subprocess.run") as mock_run, \
                 mock.patch("holler.cli.commands.click.echo"), \
                 mock.patch("holler.cli.commands.click.secho") as mock_secho:
                # Ensure HOLLER_COMPOSE_FILE not set
                os.environ.pop("HOLLER_COMPOSE_FILE", None)
                _start_services()
            # subprocess.run must NOT have been called
            assert not mock_run.called, "subprocess.run should not be called when compose file missing"
            # An error message must have been printed
            error_calls = [
                c for c in mock_secho.call_args_list
                if c[1].get("fg") == "red"
            ]
            assert len(error_calls) > 0, "Expected red error message when docker-compose.yml not found"
            error_text = " ".join(str(c[0][0]) for c in error_calls)
            # Error should mention the project directory or HOLLER_COMPOSE_FILE
            assert "holler" in error_text.lower() or "docker" in error_text.lower() or "HOLLER_COMPOSE_FILE" in error_text
        finally:
            os.chdir(orig_cwd)


class TestEnvVarAlignment:
    """Env var names are consistent between CLI, docker-compose, and FreeSWITCH config."""

    def test_external_xml_uses_holler_trunk_vars(self):
        """FreeSWITCH external.xml must use HOLLER_TRUNK_* var names (per D-03)."""
        xml_path = Path(__file__).resolve().parent.parent / "config" / "freeswitch" / "sip_profiles" / "external.xml"
        content = xml_path.read_text()
        assert "HOLLER_TRUNK_HOST" in content
        assert "HOLLER_TRUNK_USER" in content
        assert "HOLLER_TRUNK_PASS" in content
        # Old names must NOT be present
        assert "TRUNK_PASSWORD" not in content
        assert "value=\"$${TRUNK_USER}\"" not in content
        assert "value=\"$${TRUNK_HOST}\"" not in content

    def test_docker_compose_injects_trunk_vars(self):
        """docker-compose.yml must inject HOLLER_TRUNK_* into freeswitch container (per D-02)."""
        compose_path = Path(__file__).resolve().parent.parent / "docker" / "docker-compose.yml"
        content = compose_path.read_text()
        assert "HOLLER_TRUNK_HOST" in content
        assert "HOLLER_TRUNK_USER" in content
        assert "HOLLER_TRUNK_PASS" in content

    def test_cli_writes_same_var_names_as_freeswitch_reads(self):
        """CLI trunk vars must match FreeSWITCH XML var names."""
        # CLI writes these keys (from _write_trunk_config)
        cli_keys = {"HOLLER_TRUNK_HOST", "HOLLER_TRUNK_USER", "HOLLER_TRUNK_PASS"}
        # FreeSWITCH reads these (parse from external.xml)
        xml_path = Path(__file__).resolve().parent.parent / "config" / "freeswitch" / "sip_profiles" / "external.xml"
        content = xml_path.read_text()
        for key in cli_keys:
            assert key in content, f"{key} not found in external.xml"


class TestHollerConfigSMSField:
    """HollerConfig.from_env() returns config with sms field populated."""

    def test_config_has_sms_field(self):
        from holler.config import HollerConfig
        fields = HollerConfig.__dataclass_fields__
        assert "sms" in fields

    def test_from_env_returns_sms_config(self):
        from holler.config import HollerConfig
        from holler.core.sms.client import SMSConfig
        with mock.patch("dotenv.load_dotenv"), \
             mock.patch.dict(os.environ, {}, clear=False):
            config = HollerConfig.from_env()
        assert isinstance(config.sms, SMSConfig)

    def test_from_env_reads_smsc_host_env_var(self):
        from holler.config import HollerConfig
        with mock.patch("dotenv.load_dotenv"), \
             mock.patch.dict(os.environ, {"HOLLER_SMSC_HOST": "10.0.0.99"}):
            config = HollerConfig.from_env()
        assert config.sms.smsc_host == "10.0.0.99"

    def test_from_env_reads_smsc_port_env_var(self):
        from holler.config import HollerConfig
        with mock.patch("dotenv.load_dotenv"), \
             mock.patch.dict(os.environ, {"HOLLER_SMSC_PORT": "2776"}):
            config = HollerConfig.from_env()
        assert config.sms.smsc_port == 2776

    def test_from_env_loads_dotenv_file(self):
        from holler.config import HollerConfig
        with mock.patch("dotenv.load_dotenv") as mock_dotenv:
            HollerConfig.from_env()
        mock_dotenv.assert_called_once_with(".holler.env", override=False)
