"""Swarm orchestrator — schedules and runs agents concurrently.

Two-phase execution:
  1. **Independent phase**: All enabled agents run in parallel on the
     raw extractions.  Results are published to the :class:`MessageBus`.
  2. **Synthesis phase**: A final synthesis step collects all agent
     outputs and produces a unified analysis.

The orchestrator returns a merged result dict keyed by agent role,
plus a ``_swarm_meta`` key with run statistics.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from ppke.pipeline.swarm.agents import Agent, BUILTIN_AGENTS
from ppke.pipeline.swarm.bus import MessageBus

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str], None]


class SwarmOrchestrator:
    """Schedules agents and manages their execution.

    Args:
        agents: List of :class:`Agent` instances to run.  Defaults to all
            built-in agents.
        max_workers: Maximum concurrent agent threads.
    """

    def __init__(
        self,
        agents: list[Agent] | None = None,
        max_workers: int = 4,
    ) -> None:
        self.agents = agents or list(BUILTIN_AGENTS.values())
        self.max_workers = max_workers
        self.bus = MessageBus()

    def run(
        self,
        client: Any,
        extractions: list[Any],
        book_title: str,
        book_author: str,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Execute all enabled agents and return merged results.

        Returns:
            Dict mapping agent role -> analysis result, plus ``_swarm_meta``
            with timing and statistics.
        """
        enabled_agents = [a for a in self.agents if a.enabled]
        if not enabled_agents:
            logger.warning("No enabled agents for swarm run")
            return {"_swarm_meta": {"agents_run": 0, "mode": "swarm"}}

        def _progress(detail: str) -> None:
            if progress_callback:
                progress_callback("swarm", detail)
            logger.info("[swarm] %s", detail)

        _progress(
            f"Starting swarm with {len(enabled_agents)} agents "
            f"(max {self.max_workers} workers)"
        )

        self.bus.clear()
        merged: dict[str, Any] = {}
        start_time = time.time()
        agent_timings: dict[str, float] = {}

        # Phase 1: Run agents concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for agent in enabled_agents:
                _progress(f"Launching agent: {agent.name}")
                context = self.bus.context_for(agent.role.value)
                future = executor.submit(
                    agent.run,
                    client,
                    extractions,
                    book_title,
                    book_author,
                    context,
                )
                futures[future] = agent

            for future in as_completed(futures):
                agent = futures[future]
                agent_start = time.time()
                try:
                    result = future.result()
                    merged.update(result)
                    # Publish results to bus for potential cross-referencing
                    self.bus.publish(
                        sender=agent.role.value,
                        topic="analysis",
                        payload=result.get(agent.role.value, {}),
                    )
                    _progress(f"Agent {agent.name} completed")
                except Exception as exc:
                    logger.exception("Agent %s failed: %s", agent.name, exc)
                    merged[agent.role.value] = {"error": str(exc)}
                    _progress(f"Agent {agent.name} failed: {exc}")
                finally:
                    agent_timings[agent.role.value] = time.time() - agent_start

        total_time = time.time() - start_time

        # Add swarm metadata
        merged["_swarm_meta"] = {
            "mode": "swarm",
            "agents_run": len(enabled_agents),
            "agent_names": [a.name for a in enabled_agents],
            "agent_roles": [a.role.value for a in enabled_agents],
            "agent_timings": agent_timings,
            "total_time_seconds": round(total_time, 2),
            "messages_exchanged": self.bus.message_count,
        }

        _progress(
            f"Swarm complete: {len(enabled_agents)} agents, "
            f"{total_time:.1f}s total, {self.bus.message_count} messages"
        )

        return merged
