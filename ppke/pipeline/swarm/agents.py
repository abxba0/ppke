"""Agent definitions for the Swarm pipeline.

Each agent is a specialised processing unit that receives extractions and
produces analysis results.  Agents declare their *role* so the scheduler
can group them and route inter-agent messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Built-in agent roles for the Swarm pipeline."""

    ARCHITECT = "architect"
    SECURITY_AUDITOR = "security_auditor"
    FACT_CHECKER = "fact_checker"
    CODE_REVIEWER = "code_reviewer"
    CONCEPT_ANALYST = "concept_analyst"
    PATTERN_DETECTOR = "pattern_detector"


@dataclass
class Agent:
    """A specialised processing agent.

    Attributes:
        role: The agent's role enum.
        name: Human-readable display name.
        description: Short description of what this agent does.
        system_prompt: System-level prompt used when calling the LLM.
        enabled: Whether the agent is active in the current run.
    """

    role: AgentRole
    name: str
    description: str
    system_prompt: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def run(
        self,
        client: Any,
        extractions: list[Any],
        book_title: str,
        book_author: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute this agent's analysis on the provided extractions.

        Uses the LLM client with the agent's system prompt to produce
        structured output.  ``context`` carries messages from other agents
        via the :class:`MessageBus`.

        Returns a dict with analysis results keyed by the agent's role.
        """
        logger.info("Agent %s (%s) starting analysis", self.name, self.role.value)

        user_prompt = (
            f"Analyze the following extractions from '{book_title}' by {book_author}.\n"
            f"You are acting as: {self.name} — {self.description}\n\n"
        )

        if context:
            user_prompt += "Context from other agents:\n"
            for key, value in context.items():
                user_prompt += f"  - {key}: {value}\n"
            user_prompt += "\n"

        extraction_texts = []
        for ext in extractions[:50]:  # Limit to avoid context overflow
            text = getattr(ext, "original_text", str(ext))
            extraction_texts.append(text)

        user_prompt += "Extractions:\n" + "\n---\n".join(extraction_texts)

        try:
            result = client.complete_json(
                system=self.system_prompt or f"You are a {self.name}.",
                user=user_prompt,
            )
        except Exception as exc:
            logger.warning("Agent %s failed: %s", self.name, exc)
            result = {"error": str(exc)}

        return {self.role.value: result}


# ── Built-in agent definitions ──

BUILTIN_AGENTS: dict[str, Agent] = {
    AgentRole.ARCHITECT.value: Agent(
        role=AgentRole.ARCHITECT,
        name="Architect",
        description="Analyses the overall logical structure and argument flow of the document.",
        system_prompt=(
            "You are an expert document architect. Identify the central thesis, "
            "key argument threads, logical dependencies, and structural patterns. "
            "Return structured JSON with keys: central_thesis, argument_threads, "
            "structural_patterns, logical_gaps."
        ),
    ),
    AgentRole.SECURITY_AUDITOR.value: Agent(
        role=AgentRole.SECURITY_AUDITOR,
        name="Security Auditor",
        description="Scans for security-relevant patterns, vulnerabilities, and risk factors in technical content.",
        system_prompt=(
            "You are a security auditor. Identify security-relevant patterns, "
            "potential vulnerabilities, risk factors, and security recommendations. "
            "Return structured JSON with keys: risks, vulnerabilities, "
            "recommendations, severity_assessment."
        ),
    ),
    AgentRole.FACT_CHECKER.value: Agent(
        role=AgentRole.FACT_CHECKER,
        name="Fact-Checker",
        description="Verifies factual claims, identifies unsupported assertions, and flags contradictions.",
        system_prompt=(
            "You are a rigorous fact-checker. Identify factual claims, assess their "
            "support level, flag unsupported assertions and contradictions. "
            "Return structured JSON with keys: verified_claims, unsupported_claims, "
            "contradictions, confidence_scores."
        ),
    ),
    AgentRole.CODE_REVIEWER.value: Agent(
        role=AgentRole.CODE_REVIEWER,
        name="Code Reviewer",
        description="Reviews code quality, patterns, and best practices in technical documents.",
        system_prompt=(
            "You are an expert code reviewer. Analyze code quality, design patterns, "
            "best practices adherence, and improvement suggestions. "
            "Return structured JSON with keys: code_quality, patterns_found, "
            "improvements, best_practices_violations."
        ),
    ),
    AgentRole.CONCEPT_ANALYST.value: Agent(
        role=AgentRole.CONCEPT_ANALYST,
        name="Concept Analyst",
        description="Deep-dives into concept definitions, relationships, and ontological mappings.",
        system_prompt=(
            "You are a concept analysis expert. Identify key concepts, their "
            "definitions, inter-relationships, and ontological category. "
            "Return structured JSON with keys: concepts, relationships, "
            "ontology, concept_map."
        ),
    ),
    AgentRole.PATTERN_DETECTOR.value: Agent(
        role=AgentRole.PATTERN_DETECTOR,
        name="Pattern Detector",
        description="Detects recurring patterns, themes, and structural motifs across the document.",
        system_prompt=(
            "You are a pattern detection specialist. Identify recurring themes, "
            "structural motifs, rhetorical patterns, and statistical regularities. "
            "Return structured JSON with keys: themes, motifs, rhetorical_patterns, "
            "frequency_analysis."
        ),
    ),
}
