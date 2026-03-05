"""Tests for the dual-mode orchestrator feature.

Tests cover:
- Config processing_mode persistence (save/load)
- CLI --mode flag for ingest commands
- Swarm module: agents, bus, orchestrator
- Processing mode in config --show
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ppke.cli import main
from ppke.config import Config, LLMConfig, PROCESSING_MODES


# ── Config tests ──


class TestConfigProcessingMode:
    """Test processing_mode field in Config."""

    def test_default_processing_mode(self):
        cfg = Config()
        assert cfg.processing_mode == "linear"

    def test_processing_modes_tuple(self):
        assert "linear" in PROCESSING_MODES
        assert "swarm" in PROCESSING_MODES

    def test_save_and_load_processing_mode(self, tmp_path):
        cfg = Config(processing_mode="swarm")
        cfg_path = tmp_path / "config.json"
        cfg.save(cfg_path)

        loaded = Config.load(cfg_path)
        assert loaded.processing_mode == "swarm"

    def test_save_linear_mode(self, tmp_path):
        cfg = Config(processing_mode="linear")
        cfg_path = tmp_path / "config.json"
        cfg.save(cfg_path)

        data = json.loads(cfg_path.read_text())
        assert data["processing_mode"] == "linear"

    def test_load_missing_processing_mode_defaults_linear(self, tmp_path):
        """Old config files without processing_mode should default to linear."""
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"vault_path": str(tmp_path)}))
        loaded = Config.load(cfg_path)
        assert loaded.processing_mode == "linear"


# ── CLI tests ──


class TestCLIModeFlag:
    """Test --mode flag on CLI commands."""

    def test_ingest_help_shows_mode(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output
        assert "linear" in result.output
        assert "swarm" in result.output

    def test_ingest_pr_help_shows_mode(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ingest-pr", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output

    def test_async_ingest_help_shows_mode(self):
        runner = CliRunner()
        result = runner.invoke(main, ["async-ingest", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output

    def test_config_show_displays_processing_mode(self):
        runner = CliRunner()
        cfg = Config(processing_mode="swarm")
        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["config", "--show"])
        assert result.exit_code == 0
        assert "Processing mode:" in result.output
        assert "swarm" in result.output

    def test_config_show_displays_linear_by_default(self):
        runner = CliRunner()
        cfg = Config()
        with patch("ppke.cli.Config.load", return_value=cfg):
            result = runner.invoke(main, ["config", "--show"])
        assert result.exit_code == 0
        assert "Processing mode:" in result.output
        assert "linear" in result.output

    def test_config_set_processing_mode(self):
        runner = CliRunner()
        cfg = Config()
        with patch("ppke.cli.Config.load", return_value=cfg), \
             patch.object(Config, "save"):
            result = runner.invoke(main, ["config", "--processing-mode", "swarm"])
        assert result.exit_code == 0
        assert cfg.processing_mode == "swarm"

    def test_config_help_shows_processing_mode(self):
        runner = CliRunner()
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "--processing-mode" in result.output


# ── Swarm module tests ──


class TestSwarmAgents:
    """Test swarm agent definitions."""

    def test_builtin_agents_exist(self):
        from ppke.pipeline.swarm.agents import BUILTIN_AGENTS, AgentRole
        assert len(BUILTIN_AGENTS) > 0
        assert AgentRole.ARCHITECT.value in BUILTIN_AGENTS
        assert AgentRole.SECURITY_AUDITOR.value in BUILTIN_AGENTS
        assert AgentRole.FACT_CHECKER.value in BUILTIN_AGENTS

    def test_agent_roles_enum(self):
        from ppke.pipeline.swarm.agents import AgentRole
        assert AgentRole.ARCHITECT.value == "architect"
        assert AgentRole.SECURITY_AUDITOR.value == "security_auditor"
        assert AgentRole.FACT_CHECKER.value == "fact_checker"
        assert AgentRole.CODE_REVIEWER.value == "code_reviewer"
        assert AgentRole.CONCEPT_ANALYST.value == "concept_analyst"
        assert AgentRole.PATTERN_DETECTOR.value == "pattern_detector"

    def test_agent_run_calls_llm(self):
        from ppke.pipeline.swarm.agents import Agent, AgentRole
        agent = Agent(
            role=AgentRole.ARCHITECT,
            name="Test Agent",
            description="Test description",
            system_prompt="You are a test agent.",
        )
        mock_client = MagicMock()
        mock_client.complete_json.return_value = {"test": "result"}

        result = agent.run(mock_client, [], "Test Book", "Test Author")
        assert "architect" in result
        assert result["architect"] == {"test": "result"}
        mock_client.complete_json.assert_called_once()

    def test_agent_run_handles_error(self):
        from ppke.pipeline.swarm.agents import Agent, AgentRole
        agent = Agent(
            role=AgentRole.ARCHITECT,
            name="Test Agent",
            description="Test description",
        )
        mock_client = MagicMock()
        mock_client.complete_json.side_effect = RuntimeError("LLM error")

        result = agent.run(mock_client, [], "Test Book", "Test Author")
        assert "architect" in result
        assert "error" in result["architect"]

    def test_agent_run_with_context(self):
        from ppke.pipeline.swarm.agents import Agent, AgentRole
        agent = Agent(
            role=AgentRole.FACT_CHECKER,
            name="Fact-Checker",
            description="Checks facts",
        )
        mock_client = MagicMock()
        mock_client.complete_json.return_value = {"facts": []}

        context = {"architect:analysis": {"thesis": "test"}}
        result = agent.run(mock_client, [], "Book", "Author", context=context)
        assert "fact_checker" in result

    def test_agent_disabled(self):
        from ppke.pipeline.swarm.agents import Agent, AgentRole
        agent = Agent(
            role=AgentRole.ARCHITECT,
            name="Test",
            description="Test",
            enabled=False,
        )
        assert not agent.enabled


class TestSwarmMessageBus:
    """Test the inter-agent communication bus."""

    def test_publish_and_collect(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        bus.publish("agent1", "analysis", {"key": "value"})
        msgs = bus.collect()
        assert len(msgs) == 1
        assert msgs[0].sender == "agent1"
        assert msgs[0].payload == {"key": "value"}

    def test_collect_by_topic(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        bus.publish("a1", "analysis", {"a": 1})
        bus.publish("a2", "validation", {"b": 2})
        msgs = bus.collect(topic="analysis")
        assert len(msgs) == 1
        assert msgs[0].sender == "a1"

    def test_collect_exclude_sender(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        bus.publish("a1", "analysis", {"a": 1})
        bus.publish("a2", "analysis", {"b": 2})
        msgs = bus.collect(exclude_sender="a1")
        assert len(msgs) == 1
        assert msgs[0].sender == "a2"

    def test_context_for_agent(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        bus.publish("architect", "analysis", {"thesis": "test"})
        bus.publish("fact_checker", "analysis", {"facts": []})
        context = bus.context_for("architect")
        assert "fact_checker:analysis" in context
        assert "architect:analysis" not in context

    def test_message_count(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        assert bus.message_count == 0
        bus.publish("a", "t", "p")
        assert bus.message_count == 1

    def test_clear(self):
        from ppke.pipeline.swarm.bus import MessageBus
        bus = MessageBus()
        bus.publish("a", "t", "p")
        bus.clear()
        assert bus.message_count == 0


class TestSwarmOrchestrator:
    """Test the swarm orchestrator."""

    def test_run_with_agents(self):
        from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator
        from ppke.pipeline.swarm.agents import Agent, AgentRole

        agents = [
            Agent(role=AgentRole.ARCHITECT, name="A", description="D"),
            Agent(role=AgentRole.FACT_CHECKER, name="FC", description="D"),
        ]

        mock_client = MagicMock()
        mock_client.complete_json.return_value = {"result": "ok"}

        orchestrator = SwarmOrchestrator(agents=agents, max_workers=2)
        results = orchestrator.run(mock_client, [], "Book", "Author")

        assert "_swarm_meta" in results
        assert results["_swarm_meta"]["mode"] == "swarm"
        assert results["_swarm_meta"]["agents_run"] == 2
        assert "architect" in results
        assert "fact_checker" in results

    def test_run_with_no_enabled_agents(self):
        from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator
        from ppke.pipeline.swarm.agents import Agent, AgentRole

        agents = [
            Agent(role=AgentRole.ARCHITECT, name="A", description="D", enabled=False),
        ]

        orchestrator = SwarmOrchestrator(agents=agents)
        results = orchestrator.run(MagicMock(), [], "Book", "Author")

        assert results["_swarm_meta"]["agents_run"] == 0

    def test_run_with_progress_callback(self):
        from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator
        from ppke.pipeline.swarm.agents import Agent, AgentRole

        agents = [
            Agent(role=AgentRole.ARCHITECT, name="A", description="D"),
        ]

        mock_client = MagicMock()
        mock_client.complete_json.return_value = {"r": "ok"}

        progress_log = []

        def progress_cb(stage, detail):
            progress_log.append((stage, detail))

        orchestrator = SwarmOrchestrator(agents=agents, max_workers=1)
        orchestrator.run(mock_client, [], "Book", "Author", progress_callback=progress_cb)

        assert len(progress_log) > 0
        assert any("swarm" in stage for stage, _ in progress_log)

    def test_swarm_meta_includes_timing(self):
        from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator
        from ppke.pipeline.swarm.agents import Agent, AgentRole

        agents = [
            Agent(role=AgentRole.ARCHITECT, name="A", description="D"),
        ]

        mock_client = MagicMock()
        mock_client.complete_json.return_value = {"r": "ok"}

        orchestrator = SwarmOrchestrator(agents=agents, max_workers=1)
        results = orchestrator.run(mock_client, [], "Book", "Author")

        meta = results["_swarm_meta"]
        assert "total_time_seconds" in meta
        assert "agent_timings" in meta
        assert "messages_exchanged" in meta
        assert isinstance(meta["total_time_seconds"], float)

    def test_default_agents_loaded(self):
        from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator
        orchestrator = SwarmOrchestrator()
        assert len(orchestrator.agents) > 0

    def test_swarm_module_imports(self):
        """Test that the swarm module can be imported via the package."""
        from ppke.pipeline.swarm import Agent, AgentRole, BUILTIN_AGENTS, MessageBus, SwarmOrchestrator
        assert Agent is not None
        assert AgentRole is not None
        assert BUILTIN_AGENTS is not None
        assert MessageBus is not None
        assert SwarmOrchestrator is not None
