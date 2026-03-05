"""Swarm (multi-agent) processing pipeline.

Provides an agentic orchestrator that runs specialized agents concurrently,
with inter-agent communication via a shared message bus.
"""

from ppke.pipeline.swarm.agents import Agent, AgentRole, BUILTIN_AGENTS
from ppke.pipeline.swarm.bus import MessageBus
from ppke.pipeline.swarm.orchestrator import SwarmOrchestrator

__all__ = [
    "Agent",
    "AgentRole",
    "BUILTIN_AGENTS",
    "MessageBus",
    "SwarmOrchestrator",
]
