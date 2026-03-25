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
