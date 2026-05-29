# PPKE Persona Layer — Full Build Metaprompt

**Purpose:** This document is a complete specification for adding a persona layer on top of the
existing PPKE codebase (path 1 fork). Hand this to an LLM coding assistant (Claude Code, Cursor,
etc.) as the authoritative build brief. Every section is meant to be implementation-ready.

---

## 0. Context: What PPKE Already Gives You

Before building anything, understand what is already in place so you do not duplicate it.

PPKE's existing vault structure for each ingested book produces:

```
Book_<Title>_<Author>_<Year>/
├── meta.yml                  ← book metadata, ingestion status
├── extractions.json          ← raw per-paragraph extraction data
├── 01_Raw_Structure.md       ← full verbatim text + all extraction fields
├── 02_Logical_Map.md         ← argument architecture
├── 03_Concept_Index.md       ← concept tracking across chapters
├── 04_Author_Model.md        ← author analysis (voice, style, positions)
├── 05_Coverage_Report.md     ← validation report
└── 06_Patterns.md            ← patterns, tensions, metaphors, contradictions
```

Global vault files:

```
~/KnowledgeBase/
├── MASTER_CONCEPT_INDEX.md   ← cross-book, semantically deduplicated
├── QA_RESULTS.md             ← coverage status
└── RESEARCH_NOTEBOOK.md      ← per-query log
```

The persona layer reads from these files. It does NOT re-ingest or re-extract. The PPKE
pipeline is upstream infrastructure; the persona layer is downstream intelligence.

---

## 1. Goal

Add a `ppke/persona/` module and associated CLI commands that allow a user to:

1. **Define** a persona — a named, persistent entity whose beliefs, reasoning style, and voice
   are synthesized from one or more ingested PPKE book vaults.
2. **Interact** with the persona — ask it questions, give it tasks, have it reason through
   problems — and receive responses that are grounded in the source knowledge AND expressed
   in the persona's characteristic voice.
3. **Maintain session memory** — the persona accumulates what has been discussed across
   sessions, resolves contradictions, and does not start from zero each time.
4. **Run in agent mode** — beyond Q&A, the persona can be given tasks ("analyse this argument",
   "write a reflection on X", "compare your view with this passage") and execute them.

---

## 2. New Directory Structure

Add the following to the existing `ppke/` tree. Do not modify any existing file unless
explicitly instructed in section 9 (Integration Points).

```
ppke/
└── persona/
    ├── __init__.py
    ├── models.py            ← Pydantic models for all persona data structures
    ← kernel_builder.py     ← synthesises PERSONA_KERNEL.md from vault files
    ├── kernel_builder.py
    ├── memory.py            ← session memory: read, write, resolve contradictions
    ├── engine.py            ← core query/task execution with persona framing
    ├── agent.py             ← agentic task loop (multi-step reasoning + execution)
    ├── prompts.py           ← all persona-layer prompt templates (NO inline prompts elsewhere)
    └── cli.py               ← Click commands: persona-build, persona-chat, persona-task, etc.
```

New vault files created by this layer:

```
~/KnowledgeBase/
├── personas/
│   └── <persona_name>/
│       ├── PERSONA_KERNEL.md          ← synthesised identity document (core)
│       ├── PERSONA_MEMORY.jsonl       ← append-only session memory log
│       ├── PERSONA_MEMORY_SUMMARY.md  ← rolling LLM-compressed summary of memory
│       ├── PERSONA_SOURCES.yml        ← which books feed this persona + weights
│       └── PERSONA_SESSIONS/
│           └── session_<ISO_timestamp>.md  ← per-session transcript
```

---

## 3. Data Models (`ppke/persona/models.py`)

Implement all models using Pydantic v2. Every model must be serialisable to/from JSON.

```python
# ppke/persona/models.py

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class PersonaSource(BaseModel):
    """One book vault that feeds this persona."""
    book_folder: str           # e.g. "Book_Being_and_Time_Heidegger_1927"
    weight: float = 1.0        # relative influence weight (default equal)
    role: str = "primary"      # "primary" | "secondary" | "contrast"
    # "contrast" = used for dialectical tension, not voice synthesis


class PersonaKernel(BaseModel):
    """
    The synthesised identity of the persona. Lives in PERSONA_KERNEL.md.
    This is the ALWAYS-LOADED context — it goes into every prompt.
    Keep it under 3000 tokens total.
    """
    name: str
    tagline: str                        # one sentence: who is this persona?
    core_beliefs: list[str]             # 5–10 fundamental positions, each ≤ 40 words
    reasoning_style: str                # how this thinker constructs arguments, ≤ 200 words
    characteristic_moves: list[str]     # rhetorical patterns, e.g. "always grounds abstractions
                                        # in concrete examples", ≤ 5 items
    vocabulary_register: str            # formal/poetic/dialectical/systematic/aphoristic/etc.
    known_tensions: list[str]           # internal contradictions in the source material, ≤ 5
    epistemic_stance: str               # how certain/uncertain/provisional this thinker is
    what_this_thinker_rejects: list[str]  # positions explicitly argued against, ≤ 5
    synthesis_sources: list[str]        # book folders that produced this kernel
    kernel_version: int = 1
    built_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class MemoryEntry(BaseModel):
    """One unit of episodic memory. Appended to PERSONA_MEMORY.jsonl."""
    entry_id: str                      # UUID
    session_id: str
    timestamp: datetime
    entry_type: str                    # "belief_confirmed" | "belief_challenged" |
                                       # "new_connection" | "contradiction_flagged" |
                                       # "task_completed" | "user_stated"
    content: str                       # the memory in plain language, ≤ 150 words
    source_query: str                  # the user input that triggered this memory
    evidence_refs: list[str]           # paragraph IDs from extractions.json if applicable
    confidence: float = 1.0            # 0.0–1.0


class MemorySummary(BaseModel):
    """Rolling compressed summary of all memory. Lives in PERSONA_MEMORY_SUMMARY.md."""
    persona_name: str
    entry_count: int
    summary_text: str                  # LLM-compressed, ≤ 800 words
    dominant_themes: list[str]
    unresolved_tensions: list[str]
    last_compressed_at: datetime
    covers_entries_up_to: str          # entry_id of last entry included


class PersonaConfig(BaseModel):
    """Lives in PERSONA_SOURCES.yml."""
    name: str
    description: str
    sources: list[PersonaSource]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    agent_mode_enabled: bool = True
    memory_compression_threshold: int = 50   # compress after N new entries
    max_retrieved_chunks: int = 8
    kernel_auto_rebuild: bool = False         # rebuild kernel when new book ingested


class QueryContext(BaseModel):
    """Assembled context for a single query/task. Internal use only."""
    kernel: PersonaKernel
    memory_summary: str                # text of PERSONA_MEMORY_SUMMARY.md or "" if empty
    recent_memory_entries: list[MemoryEntry]  # last N entries not yet in summary
    retrieved_chunks: list[dict]       # from PPKE hybrid search: {text, source, para_id, score}
    raw_query: str
    interaction_mode: str              # "qa" | "task" | "reflection" | "dialectic"
    session_id: str
```

---

## 4. Persona Kernel Builder (`ppke/persona/kernel_builder.py`)

The kernel builder reads PPKE's existing vault outputs and synthesises the `PersonaKernel`.
This is the most important component — the quality of the kernel determines the quality of
every interaction.

### 4.1 Input reading logic

Read the following files from each source book folder in priority order:

| File | What to extract | Priority |
|------|----------------|----------|
| `04_Author_Model.md` | Voice, style, positions, epistemic stance | **Highest** |
| `02_Logical_Map.md` | Core argument structure, what is defended/attacked | High |
| `06_Patterns.md` | Characteristic rhetorical moves, tensions, metaphors | High |
| `03_Concept_Index.md` | Key concepts and how they interrelate | Medium |
| `01_Raw_Structure.md` | Verbatim passage samples for voice calibration | Medium |
| `MASTER_CONCEPT_INDEX.md` | Cross-book concept relationships | Low (multi-source only) |

### 4.2 Kernel synthesis prompt (goes in `ppke/persona/prompts.py`)

The kernel builder makes exactly TWO LLM calls per build:

**Call 1 — Per-source pass** (once per source book, uses `small_model`):
Extract a structured pre-kernel from a single book's files.

```
SYSTEM:
You are a philosophical analyst. Your task is to extract a structured profile of a thinker
from their analysed work. You will output ONLY valid JSON matching the schema provided.
Do not summarise or paraphrase — extract and distil. Every claim must be traceable to the
source material.

USER:
Given the following analysed material from "{book_title}" by {author}:

<author_model>
{content_of_04_Author_Model}
</author_model>

<logical_map>
{content_of_02_Logical_Map}
</logical_map>

<patterns>
{content_of_06_Patterns}
</patterns>

<concept_samples>
{first_500_words_of_03_Concept_Index}
</concept_samples>

Extract a pre-kernel profile as JSON with EXACTLY these fields:
{
  "core_beliefs": ["<belief 1, ≤40 words>", ...],           // 5–8 items
  "reasoning_style": "<how they argue, ≤150 words>",
  "characteristic_moves": ["<move 1>", ...],                 // 3–5 items
  "vocabulary_register": "<one of: formal | poetic | dialectical | systematic | aphoristic | analytical | phenomenological | narrative>",
  "known_tensions": ["<tension 1>", ...],                    // 2–4 items
  "epistemic_stance": "<how certain/uncertain/provisional, ≤80 words>",
  "what_this_thinker_rejects": ["<position 1>", ...],        // 3–5 items
  "voice_samples": ["<verbatim quote ≤40 words>", ...]       // 3 quotes that exemplify the voice
}

Return ONLY the JSON. No preamble, no explanation, no markdown fences.
```

**Call 2 — Synthesis pass** (once total, uses `main_model`):
Merge all per-source pre-kernels into the final PersonaKernel.

```
SYSTEM:
You are building the identity kernel for a persona system. Given one or more pre-kernel
profiles extracted from a thinker's works, synthesise a unified PersonaKernel that:
- Resolves surface contradictions where possible (note irresolvable ones in known_tensions)
- Captures the thinker's most characteristic and consistent voice
- Is concise enough to fit in a system prompt (UNDER 3000 tokens total when rendered)
- Prefers the PRIMARY source over SECONDARY; uses CONTRAST sources only for known_tensions
- Never invents positions not present in the source material
- Marks any inference with [INFERENCE]

Output ONLY valid JSON matching this exact schema:
{
  "name": "<persona name>",
  "tagline": "<one sentence: who is this persona, ≤20 words>",
  "core_beliefs": ["<belief>", ...],
  "reasoning_style": "<≤200 words>",
  "characteristic_moves": ["<move>", ...],
  "vocabulary_register": "<register>",
  "known_tensions": ["<tension>", ...],
  "epistemic_stance": "<≤100 words>",
  "what_this_thinker_rejects": ["<position>", ...],
  "synthesis_sources": ["<book_folder_1>", ...]
}

Return ONLY the JSON. No preamble, no explanation, no markdown fences.
```

### 4.3 Kernel rendering to markdown

After synthesis, render the kernel to `PERSONA_KERNEL.md` using this exact template.
This file is also what gets loaded into context at query time.

```markdown
# PERSONA KERNEL: {name}

> {tagline}

---

## Core Beliefs

{numbered list of core_beliefs}

## Reasoning Style

{reasoning_style}

## Characteristic Moves

{bulleted list of characteristic_moves}

## Vocabulary & Register

{vocabulary_register}

## Epistemic Stance

{epistemic_stance}

## Known Tensions

{numbered list of known_tensions}

## What This Thinker Rejects

{bulleted list of what_this_thinker_rejects}

---

*Synthesised from: {comma-separated synthesis_sources}*
*Kernel version: {kernel_version} | Built: {built_at ISO date}*
```

### 4.4 Public API for kernel_builder.py

```python
def build_kernel(
    persona_name: str,
    sources: list[PersonaSource],
    vault_path: Path,
    llm_client,          # existing ppke LLMClient instance
    config,              # existing ppke Config instance
    force_rebuild: bool = False
) -> PersonaKernel:
    """
    Build or rebuild the persona kernel from vault files.
    Returns the PersonaKernel and writes PERSONA_KERNEL.md to vault.
    Raises FileNotFoundError if any source book folder is missing.
    Raises ValueError if kernel synthesis returns invalid JSON.
    """

def load_kernel(persona_name: str, vault_path: Path) -> PersonaKernel:
    """
    Load an existing kernel from PERSONA_KERNEL.md.
    Raises FileNotFoundError if persona does not exist.
    """

def render_kernel_to_markdown(kernel: PersonaKernel) -> str:
    """Return the formatted markdown string (does not write to disk)."""
```

---

## 5. Memory System (`ppke/persona/memory.py`)

The memory system is append-only. It never deletes entries. Compression creates a summary
but the original JSONL is preserved.

### 5.1 Memory file layout

`PERSONA_MEMORY.jsonl` — one JSON object per line, each a `MemoryEntry`. Always append.
`PERSONA_MEMORY_SUMMARY.md` — the rolling compressed summary. Overwritten on compression.

### 5.2 Memory entry creation

The engine (section 6) is responsible for deciding WHEN to create memory entries.
The memory module is responsible for HOW to store and retrieve them.

Create a `MemoryEntry` after every interaction for:
- Any user statement about beliefs, values, or positions (`entry_type: "user_stated"`)
- Any response where the persona's belief was explicitly confirmed or challenged
- Any new conceptual connection made during the interaction
- Any contradiction identified between the user's question and the persona's known positions
- Any completed task

### 5.3 Memory retrieval for context assembly

At query time, retrieve recent memory in two layers:

**Layer 1 — Summary**: Always load `PERSONA_MEMORY_SUMMARY.md` in full if it exists.
This is the compressed history of all prior sessions.

**Layer 2 — Recent raw entries**: Load the last `N` entries from `PERSONA_MEMORY.jsonl`
that are NOT yet captured in the summary (i.e., entries after `covers_entries_up_to`).
Default `N = 10`. These go into the context as-is.

### 5.4 Memory compression

Trigger compression when the number of uncompressed entries exceeds
`memory_compression_threshold` (default 50). Compression is a single LLM call.

```
SYSTEM:
You are compressing the episodic memory of a persona called "{persona_name}".
Your output will be loaded into every future context window, so be concise but complete.
Preserve all: confirmed beliefs, challenged positions, contradictions, key connections,
and ongoing themes. Discard: trivial acknowledgements, duplicated entries, one-off facts
with no pattern significance.

USER:
Existing summary (if any):
<existing_summary>
{current_summary_text or "None"}
</existing_summary>

New memory entries to integrate (in chronological order):
<new_entries>
{formatted list of new MemoryEntry objects}
</new_entries>

Output a new summary (≤800 words) followed by these exact fields on separate lines:
DOMINANT_THEMES: theme1 | theme2 | theme3
UNRESOLVED_TENSIONS: tension1 | tension2

No other output. No preamble.
```

### 5.5 Public API for memory.py

```python
def append_memory(
    entry: MemoryEntry,
    persona_name: str,
    vault_path: Path
) -> None:
    """Append one memory entry to PERSONA_MEMORY.jsonl. Thread-safe via file lock."""

def load_memory_context(
    persona_name: str,
    vault_path: Path,
    max_recent: int = 10
) -> tuple[str, list[MemoryEntry]]:
    """
    Returns (summary_text, recent_uncompressed_entries).
    summary_text is "" if no summary exists yet.
    """

def compress_memory_if_needed(
    persona_name: str,
    vault_path: Path,
    llm_client,
    config,
    threshold: int = 50
) -> bool:
    """
    Check if compression threshold is exceeded. If so, compress and return True.
    Otherwise return False. Safe to call after every interaction.
    """

def get_memory_stats(persona_name: str, vault_path: Path) -> dict:
    """Return {total_entries, uncompressed_entries, last_session_id, dominant_themes}."""
```

---

## 6. Persona Engine (`ppke/persona/engine.py`)

The engine is the core of every interaction. It assembles context from kernel + memory +
retrieved knowledge, calls the LLM with the correct persona framing, extracts new memory
entries from the response, and returns a structured result.

### 6.1 Context assembly pipeline

Every call to `engine.query()` or `engine.run_task()` executes this sequence:

```
1. Load kernel (from disk cache if not already in memory)
2. Load memory context (summary + recent entries)
3. Rewrite query for retrieval
   → Use a single LLM call (small_model) to expand the raw query into
     2–3 search variants optimised for PPKE's hybrid search
4. Execute hybrid search across all source book vaults
   → Call ppke's existing hybrid_search() for each variant
   → Merge results, deduplicate by para_id, keep top max_retrieved_chunks
5. Assemble QueryContext
6. Build system prompt from kernel + interaction_mode
7. Build user turn from query + context
8. Call LLM (main_model)
9. Post-process response: extract memory entries, format output
10. Append memory entries
11. Trigger memory compression check
12. Write session transcript
13. Return PersonaResponse
```

### 6.2 System prompt construction

The system prompt is built dynamically from the persona kernel. It is NOT a hardcoded string.
Build it in `ppke/persona/prompts.py` as a function:

```python
def build_persona_system_prompt(
    kernel: PersonaKernel,
    interaction_mode: str,     # "qa" | "task" | "reflection" | "dialectic"
    memory_summary: str,
    recent_memory: list[MemoryEntry]
) -> str:
```

The system prompt has FOUR sections in this exact order:

**Section 1 — Identity declaration** (~200 tokens):
```
You are {name}. {tagline}

Your core positions:
{numbered list of core_beliefs}

Your reasoning style:
{reasoning_style}

Your characteristic moves:
{bulleted list of characteristic_moves}

You speak in a {vocabulary_register} register.

Your epistemic stance:
{epistemic_stance}

Positions you reject:
{bulleted list of what_this_thinker_rejects}
```

**Section 2 — Operating rules** (~150 tokens):
```
OPERATING RULES:
1. You respond AS this thinker — not as an assistant describing this thinker.
   Use first person. Never say "according to {name}" or "this thinker believes".
2. Every substantive claim must be grounded in your retrieved knowledge.
   If you cannot ground a claim, mark it [INFERENCE] and reason from first principles
   consistent with your known positions.
3. You may acknowledge uncertainty. Your epistemic stance is part of your identity.
4. Known tensions in your thought are real — do not paper over them. Acknowledge them
   when they are relevant to the question.
5. If asked something entirely outside your source knowledge, say so honestly and reason
   from analogy to what you do know.
6. Never invent citations, page numbers, or quotes. Reference ideas, not invented text.
7. If you are challenged with a position you reject, engage it seriously — do not dismiss.
```

**Section 3 — Memory context** (variable, only if non-empty):
```
MEMORY OF PRIOR INTERACTIONS:
{memory_summary if non-empty}

Recent (not yet summarised):
{formatted recent_memory entries if any}
```

**Section 4 — Mode-specific instruction** (~80 tokens, varies by mode):

- **qa mode**: "Answer the question. Cite the paragraph IDs of evidence you use in the format
  [source: {book_folder}/{para_id}]. Keep responses focused but do not truncate your reasoning."

- **task mode**: "Complete the task step by step. Think through it as this thinker would.
  Use retrieved evidence where relevant. End with a TASK_COMPLETE marker and a one-sentence summary."

- **reflection mode**: "Reflect on this topic as this thinker in a meditative, first-person mode.
  Draw on your characteristic metaphors and rhetorical patterns. This is not a Q&A response —
  it is this thinker thinking aloud."

- **dialectic mode**: "You will engage with a position that may or may not align with yours.
  Steelman it first. Then respond from your own position. Be willing to be moved if the
  argument is sound — mark any genuine updates with [UPDATE TO PRIOR POSITION]."

### 6.3 User turn construction

The user turn assembles:

```
RETRIEVED KNOWLEDGE:
{for each retrieved chunk:}
[{book_folder} / {para_id}] (relevance: {score:.2f})
{chunk_text}
---

QUERY:
{raw_query}
```

If retrieved chunks are empty (no relevant passages found), add:
```
NOTE: No directly relevant passages were retrieved. Reason from your known positions.
```

### 6.4 Query rewriting for retrieval

Before calling PPKE's hybrid search, rewrite the user's query into retrieval-optimised
variants. This is a single `small_model` call:

```
SYSTEM:
You generate search queries for a hybrid (BM25 + vector) search engine over philosophical
and psychological texts. Given a user's question or task, generate 2–3 search variants that
will surface the most relevant passages. Output as JSON array of strings. Nothing else.

USER:
Persona name: {name}
Source books: {list of book titles}
User input: {raw_query}

Output 2–3 search query strings as a JSON array. Example: ["query 1", "query 2", "query 3"]
```

### 6.5 Memory entry extraction

After every LLM response, make one additional `small_model` call to extract memory entries:

```
SYSTEM:
You extract memory-worthy moments from an AI persona interaction. Output ONLY a JSON array
of memory entries. Each entry has: {entry_type, content, evidence_refs, confidence}.
Valid entry_types: belief_confirmed | belief_challenged | new_connection |
contradiction_flagged | task_completed | user_stated.
Output [] if nothing is memory-worthy. No preamble.

USER:
Persona name: {name}
User said: {raw_query}
Persona responded: {response_text}

Extract 0–3 memory entries as a JSON array. Each must have:
{
  "entry_type": "...",
  "content": "...",       // ≤100 words, plain language
  "evidence_refs": [],    // list of para_ids mentioned in the response, can be empty
  "confidence": 0.9       // how certain this memory is
}
```

### 6.6 PersonaResponse model

```python
class PersonaResponse(BaseModel):
    persona_name: str
    session_id: str
    query: str
    response_text: str
    interaction_mode: str
    retrieved_chunks: list[dict]     # what was actually used
    memory_entries_created: list[MemoryEntry]
    citations: list[str]             # extracted para_id references from response
    inference_flags: list[str]       # any [INFERENCE] markers and their context
    tokens_used: dict                # {input, output, cache_hits}
    response_time_ms: int
```

### 6.7 Public API for engine.py

```python
class PersonaEngine:
    def __init__(
        self,
        persona_name: str,
        vault_path: Path,
        llm_client,      # existing ppke LLMClient
        config,          # existing ppke Config
    ):
        """Load kernel, initialise memory context. Raises if persona not found."""

    def query(
        self,
        question: str,
        session_id: str,
        mode: str = "qa"   # "qa" | "task" | "reflection" | "dialectic"
    ) -> PersonaResponse:
        """Single-turn interaction. Handles full context assembly + memory."""

    def run_task(
        self,
        task_description: str,
        session_id: str,
        max_steps: int = 5
    ) -> PersonaResponse:
        """
        Multi-step task execution. Calls agent.py for step decomposition.
        Returns consolidated response after all steps.
        """

    def reset_session(self) -> str:
        """Generate a new session_id. Does not clear memory."""
```

---

## 7. Agent Module (`ppke/persona/agent.py`)

The agent module handles multi-step task execution. It is only invoked by `engine.run_task()`.
Keep it simple — this is not a full ReAct loop, it is a structured task decomposer.

### 7.1 Task decomposition

When `run_task()` is called, the agent first decomposes the task into steps:

```
SYSTEM:
You are a task planner for a persona system. Given a task, break it into sequential
reasoning steps the persona should execute. Each step must be self-contained.
Output ONLY a JSON array of step descriptions. Maximum {max_steps} steps. No preamble.

USER:
Persona: {name}
Task: {task_description}
Available knowledge: {list of source book titles}

Decompose into 2–{max_steps} concrete steps. Example:
["Step 1: ...", "Step 2: ...", "Step 3: ..."]
```

### 7.2 Step execution loop

For each step, call `engine.query()` with `mode="task"` and the step description as the
query. Carry the prior step's response as additional context into the next step:

```python
prior_context = ""
step_responses = []

for i, step in enumerate(steps):
    step_query = f"{step}\n\nPrior reasoning:\n{prior_context}" if prior_context else step
    response = engine.query(step_query, session_id, mode="task")
    step_responses.append(response)
    prior_context = response.response_text
```

### 7.3 Task consolidation

After all steps, make one final `main_model` call to consolidate into a coherent response:

```
SYSTEM:
{persona system prompt — same as used in steps}

USER:
You have reasoned through the following task in steps:
ORIGINAL TASK: {task_description}

STEP RESULTS:
{for each step: "Step N: {step description}\nResult: {response_text}\n---\n"}

Now produce a single coherent response to the original task. Integrate the step reasoning
into a unified, well-structured response in your characteristic voice.
Do not list the steps — synthesise them.
```

---

## 8. CLI Commands (`ppke/persona/cli.py`)

Add a `persona` command group to the existing Click CLI in `ppke/cli.py`.
All persona commands live under `ppke persona <subcommand>`.

### 8.1 Command table

| Command | Description |
|---------|-------------|
| `ppke persona build <name>` | Build or rebuild a persona kernel from vault books |
| `ppke persona list` | List all personas in the vault |
| `ppke persona info <name>` | Show persona kernel summary and memory stats |
| `ppke persona chat <name>` | Interactive chat session with a persona |
| `ppke persona ask <name>` | Single non-interactive question |
| `ppke persona task <name>` | Give the persona a multi-step task |
| `ppke persona reflect <name>` | Free-form reflection mode |
| `ppke persona memory <name>` | View memory stats and recent entries |
| `ppke persona memory --compress <name>` | Force memory compression |
| `ppke persona memory --clear <name>` | Clear memory (requires --confirm flag) |
| `ppke persona add-source <name>` | Add a book vault as a source for this persona |

### 8.2 `ppke persona build` — detailed spec

```bash
ppke persona build <name> \
  --sources "Book_Being_and_Time_Heidegger_1927" \
  --sources "Book_Nietzsche_Zarathustra_1883:secondary" \
  --description "Heidegger's phenomenological voice" \
  [--rebuild]          # force rebuild even if kernel exists
  [--vault-path PATH]
```

- `--sources` accepts `book_folder` or `book_folder:role` (role = primary|secondary|contrast)
- If no `--sources` given, list available books and prompt interactively
- Validate each source folder exists and has `04_Author_Model.md` before starting
- Print progress: "Reading {book_title}... Running per-source extraction... Synthesising kernel..."
- On completion print: kernel tagline, belief count, source books, output path

### 8.3 `ppke persona chat` — detailed spec

```bash
ppke persona chat <name> [--mode qa|reflection|dialectic] [--vault-path PATH]
```

- Opens an interactive REPL loop (use `prompt_toolkit` if available, else simple `input()`)
- Show persona name and tagline as a header
- Each user input → `engine.query()` → print response with citations
- Special commands inside the chat:
  - `/mode qa|reflection|dialectic` — switch mode mid-session
  - `/memory` — show memory stats for this session
  - `/sources` — show which passages were retrieved for last response
  - `/save` — force-write session transcript now
  - `/quit` or Ctrl-C — end session, write transcript, run compression check
- Append each turn to `PERSONA_SESSIONS/session_<ISO_timestamp>.md`

### 8.4 `ppke persona ask` — detailed spec

```bash
ppke persona ask <name> --question "What is the relationship between anxiety and authenticity?" \
  [--mode qa]          # default qa
  [--json]             # output full PersonaResponse as JSON
  [--no-citations]     # suppress [source: ...] markers in output
  [--vault-path PATH]
```

- Single call, no REPL. Prints response to stdout.
- With `--json`: prints the full `PersonaResponse` as JSON (for pipeline use)
- Exit code 0 on success, 1 on error

### 8.5 `ppke persona task` — detailed spec

```bash
ppke persona task <name> \
  --task "Analyse the argument that authenticity requires confronting mortality. Is it sound?" \
  [--steps 5]          # max decomposition steps, default 5
  [--vault-path PATH]
```

- Runs `engine.run_task()`
- Prints step decomposition first (so user can see the plan)
- Streams each step result as it completes
- Prints consolidated response at end with `===TASK COMPLETE===` separator

---

## 9. Integration Points (Changes to Existing PPKE Files)

These are the ONLY changes to existing files. Make them minimal and non-breaking.

### 9.1 `ppke/cli.py`

Add one import and one `cli.add_command()` call:

```python
from ppke.persona.cli import persona_group
# at end of cli.py, after all existing command definitions:
cli.add_command(persona_group)
```

The `persona_group` is a Click group object defined in `ppke/persona/cli.py`:
```python
@click.group(name="persona")
def persona_group():
    """Manage and interact with AI personas built from your knowledge vault."""
```

### 9.2 `ppke/output/writer.py`

Add one new global vault file. In the `write_global_files()` function, after writing
`MASTER_CONCEPT_INDEX.md`, add a check:

```python
# Create personas directory if it doesn't exist yet
personas_dir = vault_path / "personas"
personas_dir.mkdir(exist_ok=True)
```

That's all. The persona layer manages its own files from that point.

### 9.3 `ppke/pipeline/orchestrator.py`

Add a post-ingestion hook. At the end of the orchestrator's `run()` method, after
writing all book files, emit a signal that a new book is available:

```python
# Emit post-ingestion event for any registered listeners (non-breaking)
_emit_post_ingest_event(book_folder=output_folder, vault_path=self.vault_path)
```

Implement `_emit_post_ingest_event()` as a no-op initially. The persona layer can
register a listener via `ppke.persona.kernel_builder.register_post_ingest_hook()`
which users can optionally call if `kernel_auto_rebuild = True` in their persona config.
This keeps the core pipeline decoupled from the persona layer.

### 9.4 `ppke/search.py` (or wherever hybrid_search lives)

No changes needed. The persona engine calls `hybrid_search()` directly. If the function
signature needs a `vault_path` argument, pass it from the engine. If it needs a book
filter, add it as an optional kwarg if not already present:

```python
# In hybrid_search — add if not already there:
def hybrid_search(
    query: str,
    vault_path: Path,
    book_filter: Optional[list[str]] = None,   # limit to specific book folders
    max_results: int = 20,
    ...
) -> list[dict]:
```

---

## 10. Prompt Templates (`ppke/persona/prompts.py`)

All prompts live here. No inline prompt strings anywhere else in `ppke/persona/`.

The module exports:

```python
def build_persona_system_prompt(...) -> str               # section 6.2
def build_query_rewrite_prompt(name, books, query) -> str # section 6.4
def build_memory_extract_prompt(name, query, response) -> str  # section 6.5
def build_per_source_kernel_prompt(book_title, author, ...) -> str  # section 4.2 Call 1
def build_kernel_synthesis_prompt(name, pre_kernels, sources) -> str  # section 4.2 Call 2
def build_memory_compress_prompt(name, existing_summary, new_entries) -> str  # section 5.4
def build_task_decompose_prompt(name, task, books, max_steps) -> str  # section 7.1
def build_task_consolidate_prompt(kernel_prompt, task, steps) -> str  # section 7.3
```

All prompts must follow PPKE's existing conventions:
- Anthropic cache_control tagging on system prompts (for prompt caching cost savings)
- No hardcoded model names in prompts
- No summarisation instructions (PPKE principle: verbatim preservation over efficiency)

---

## 11. Session Transcript Format

Every chat or task session writes a transcript to
`personas/<name>/PERSONA_SESSIONS/session_<ISO_timestamp>.md`.

Format:

```markdown
# Session: {session_id}
**Persona:** {name}
**Mode:** {interaction_mode}
**Date:** {ISO timestamp}
**Sources active:** {list of source book folders}

---

## Turn 1

**User:** {raw_query}

**{persona_name}:** {response_text}

*Retrieved: {comma-separated para_ids} | Memory entries created: {count}*

---

## Turn 2
...

---

## Session Summary

*Total turns: N | Memory entries: N | Tokens: {input}/{output} | Duration: Ns*
```

---

## 12. Error Handling Requirements

| Condition | Behaviour |
|-----------|-----------|
| Source book folder missing at build time | `FileNotFoundError` with clear message naming the missing folder |
| `04_Author_Model.md` missing from a source book | `ValueError`: "Book {folder} has not been fully ingested — run ppke ingest first." |
| LLM returns invalid JSON for kernel synthesis | Retry once with explicit JSON repair instruction; if still invalid, raise `ValueError` with raw LLM output attached |
| Hybrid search returns 0 results | Log warning, continue with empty retrieved_chunks, add "no retrieved evidence" note to response |
| Memory JSONL corrupt (parse error on a line) | Skip the corrupt line, log warning with line number, continue |
| Persona does not exist on `chat`/`ask`/`task` | Clear error: "Persona '{name}' not found. Run: ppke persona build {name}" |
| LLM call fails during task step | Do not abort entire task. Mark step as failed, include failure note, continue to next step |

---

## 13. Testing Requirements

Create `ppke/tests/test_persona.py`. Minimum test coverage:

| Test | What it verifies |
|------|-----------------|
| `test_kernel_build_single_source` | Kernel builds from one book vault without error; output file exists; JSON is valid |
| `test_kernel_build_multi_source` | Kernel merges two sources; known_tensions field non-empty |
| `test_kernel_load_roundtrip` | Build then load produces identical PersonaKernel |
| `test_memory_append_and_load` | Append 3 entries; load returns exactly those 3 entries |
| `test_memory_compression_trigger` | Append N > threshold entries; compress_memory_if_needed returns True; summary file written |
| `test_engine_query_returns_response` | engine.query() returns PersonaResponse with non-empty response_text |
| `test_engine_query_uses_kernel_voice` | Response text does not contain "according to {name}" or "this thinker" |
| `test_engine_no_retrieved_chunks` | Engine handles empty search results without error |
| `test_agent_task_decompose` | task decomposition returns list of step strings |
| `test_agent_task_run` | run_task returns consolidated PersonaResponse |
| `test_cli_build_command` | CLI command exits 0 and writes PERSONA_KERNEL.md |
| `test_cli_ask_command` | CLI ask exits 0, prints non-empty response to stdout |
| `test_cli_ask_json_flag` | --json flag returns parseable PersonaResponse JSON |
| `test_security_persona_name_traversal` | Persona name with `../` raises ValueError before any file access |
| `test_security_source_folder_validation` | Source folder with path components raises ValueError |

Use pytest fixtures to create a minimal mock vault with pre-written `04_Author_Model.md`
and `02_Logical_Map.md` files so tests do not require live LLM calls. Mock the LLMClient
using `unittest.mock.patch`.

---

## 14. Security Requirements

These apply on top of PPKE's existing security posture.

| Requirement | Implementation |
|-------------|---------------|
| Persona name sanitisation | Allow only `[a-zA-Z0-9_-]`, max 64 chars. Raise `ValueError` on violation. Apply before ANY file path construction. |
| Source folder sanitisation | Validate against PPKE's existing path traversal check. Must be a direct child of `vault_path`, not an arbitrary path. |
| Memory JSONL write safety | Use file lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) for concurrent write safety. |
| LLM output before file write | Never write raw LLM output directly to disk. Always parse through Pydantic model first. If parse fails, write to a `.rejected` side file for inspection. |
| No shell execution | No `subprocess` or `os.system` calls in the persona layer. |
| Kernel file integrity | On load, validate that the parsed kernel's `synthesis_sources` all still exist in the vault. Warn (not error) if a source has been removed. |
| Session transcript sanitisation | Strip any content that matches the pattern `[A-Z_]{10,}:` (potential prompt injection markers) from user input before writing to transcripts. Log the strip. |

---

## 15. Configuration Extensions

Add these fields to PPKE's existing `Config` class (in `ppke/config.py`).
All new fields are optional with sensible defaults — existing configs remain valid.

```python
# Persona layer settings — add to Config class
persona_max_retrieved_chunks: int = 8
persona_memory_compression_threshold: int = 50
persona_max_recent_memory_entries: int = 10
persona_max_task_steps: int = 5
persona_session_dir_keep_days: int = 90   # auto-archive old session files after N days
```

Expose via CLI:
```bash
ppke config --persona-chunks 12
ppke config --persona-memory-threshold 30
```

---

## 16. Build Order for Implementation

Follow this exact order to avoid dependency issues:

1. `ppke/persona/models.py` — no dependencies on other persona files
2. `ppke/persona/prompts.py` — no dependencies on other persona files (uses only models)
3. `ppke/persona/memory.py` — depends on models only
4. `ppke/persona/kernel_builder.py` — depends on models, prompts, existing LLMClient
5. `ppke/persona/engine.py` — depends on all of the above + PPKE hybrid_search
6. `ppke/persona/agent.py` — depends on engine only
7. `ppke/persona/cli.py` — depends on all of the above
8. Integration edits: `ppke/cli.py`, `ppke/output/writer.py`, `ppke/pipeline/orchestrator.py`
9. `ppke/tests/test_persona.py` — written last, tests everything above

---

## 17. Definition of Done

The persona layer is complete when ALL of the following are true:

- [ ] `ppke persona build <name> --sources <folder>` runs without error on a fully-ingested vault
- [ ] `PERSONA_KERNEL.md` is written with all required sections
- [ ] `ppke persona ask <name> --question "..."` returns a response in first-person persona voice
- [ ] The response contains at least one `[source: ...]` citation when relevant chunks exist
- [ ] `ppke persona chat <name>` opens an interactive session, multiple turns work, `/quit` writes transcript
- [ ] `ppke persona task <name> --task "..."` completes a multi-step task with consolidated output
- [ ] After 50+ interactions, `ppke persona memory --compress <name>` produces a valid summary
- [ ] On the 51st interaction, memory compression triggers automatically
- [ ] All 15 tests in `test_persona.py` pass
- [ ] `ppke doctor` does not break (add persona vault check: detect orphaned kernels)
- [ ] No existing PPKE tests are broken by the changes in section 9
