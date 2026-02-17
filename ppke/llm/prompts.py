"""Prompt templates for each PPKE skill."""

STRUCTURAL_EXTRACTION_SYSTEM = """\
You are a structural extraction engine for philosophical texts. Your job is to \
analyze paragraphs and extract structured information with absolute fidelity to \
the original text.

Rules:
- NEVER summarize or compress meaning.
- Quote exact phrases from the text as evidence.
- Mark any inference you make with [INFERENCE].
- Use the exact paragraph IDs provided.
- Return valid JSON only, no other text.
"""

STRUCTURAL_EXTRACTION_USER = """\
Analyze the following paragraphs from "{book_title}" by {author}, Chapter {chapter_num}: \
"{chapter_title}".

For each paragraph, extract:
1. topic_sentence: The main claim or topic (one sentence)
2. function_in_argument: What role this paragraph plays (e.g., "introduces thesis", \
"provides evidence", "transitions", "defines concept", "counter-argument", "conclusion")
3. explicit_claims: List of explicit claims made (quoted from text)
4. implicit_assumptions: List of unstated assumptions [INFERENCE]
5. logical_steps: Numbered sequence of reasoning steps
6. defined_concepts: Key terms or concepts introduced or used (exact phrases)
7. emotional_tone: Dominant tone (e.g., "assertive", "questioning", "polemical", "neutral")
8. tone_evidence: A quoted phrase that demonstrates the tone
9. internal_references: Any references to other parts of the text
10. is_argument_carrying: true if this paragraph carries substantive argument, false if \
transitional/contextual

Paragraphs to analyze:

{paragraphs_json}

Return a JSON array where each element has:
{{
  "paragraph_id": "<the ID>",
  "topic_sentence": "...",
  "function_in_argument": "...",
  "explicit_claims": ["..."],
  "implicit_assumptions": ["[INFERENCE] ..."],
  "logical_steps": ["1. ...", "2. ..."],
  "defined_concepts": ["..."],
  "emotional_tone": "...",
  "tone_evidence": "...",
  "internal_references": ["..."],
  "is_argument_carrying": true/false
}}

Return ONLY the JSON array. No explanation, no markdown formatting.
"""

LOGICAL_MAP_SYSTEM = """\
You are a logical architecture analyst for philosophical texts. Your job is to \
identify the central thesis, map argument structures, and trace logical chains \
through the text.

Rules:
- Every claim must be traced to specific paragraph IDs.
- Mark inferences with [INFERENCE].
- Identify circular reasoning if present.
- Map premises to conclusions explicitly.
- Return valid JSON only.
"""

LOGICAL_MAP_USER = """\
Given the following structural extraction data for "{book_title}" by {author}, \
build the logical architecture.

Extraction data:
{extraction_json}

Return JSON with:
{{
  "central_thesis": {{
    "claim": "...",
    "paragraph_ids": ["..."],
    "evidence": "..."
  }},
  "argument_threads": [
    {{
      "name": "...",
      "premises": [
        {{"claim": "...", "paragraph_ids": ["..."], "is_inference": false}}
      ],
      "conclusion": {{"claim": "...", "paragraph_ids": ["..."]}},
      "logical_issues": ["circular reasoning in...", etc.]
    }}
  ],
  "key_assumptions": [
    {{"assumption": "[INFERENCE] ...", "depends_on": ["..."]}}
  ]
}}

Return ONLY the JSON. No explanation.
"""

CONCEPT_INDEX_SYSTEM = """\
You are a concept tracking engine. You identify recurring philosophical concepts, \
track every occurrence, detect semantic drift, and build a comprehensive index.

Rules:
- Quote exact sentences for each occurrence.
- Track how concept meaning shifts across the text.
- Mark inferred semantic shifts with [INFERENCE].
- Return valid JSON only.
"""

CONCEPT_INDEX_USER = """\
Given the following structural extraction data for "{book_title}" by {author}, \
build a concept index.

Extraction data:
{extraction_json}

For each significant concept found, track:
1. Every paragraph where it appears (with the exact quote)
2. How its meaning evolves across the text
3. Related concepts

Return JSON:
{{
  "concepts": [
    {{
      "name": "...",
      "definition": "Author's definition or usage (quoted)",
      "occurrences": [
        {{"paragraph_id": "...", "quote": "...", "usage_context": "..."}}
      ],
      "semantic_shifts": [
        {{"from_id": "...", "to_id": "...", "description": "[INFERENCE] ..."}}
      ],
      "related_concepts": ["..."]
    }}
  ]
}}

Return ONLY the JSON. No explanation.
"""

PATTERN_DETECTION_SYSTEM = """\
You are a pattern and tension detector for philosophical texts. You identify \
recurring metaphors, emotional arcs, structural repetition, logical recursion, \
and internal contradictions.

Rules:
- Provide evidence with paragraph IDs for every pattern.
- Mark hypotheses with [HYPOTHESIS].
- Distinguish between explicit patterns and inferred ones.
- Return valid JSON only.
"""

PATTERN_DETECTION_USER = """\
Given the following structural extraction data for "{book_title}" by {author}, \
detect patterns and tensions.

Extraction data:
{extraction_json}

Detect:
1. Recurring metaphors (with all instances)
2. Emotional arcs (how tone shifts across chapters)
3. Structural repetition (repeated argument patterns)
4. Logical recursion (self-referential arguments)
5. Internal contradictions (conflicting claims)

Return JSON:
{{
  "patterns": [
    {{
      "type": "metaphor|emotional_arc|repetition|recursion|contradiction",
      "description": "...",
      "evidence": [
        {{"paragraph_id": "...", "quote": "..."}}
      ],
      "is_hypothesis": true/false
    }}
  ]
}}

Return ONLY the JSON. No explanation.
"""

AUTHOR_MODEL_SYSTEM = """\
You are an author model builder. Based on comprehensive structural analysis of a \
philosophical text, you construct a model of the author's intellectual framework.

Rules:
- Every claim must cite paragraph IDs.
- Mark inferences with [INFERENCE].
- Be specific, not generic.
- Return valid JSON only.
"""

AUTHOR_MODEL_USER = """\
Based on the full analysis of "{book_title}" by {author}, build an author model.

Logical map:
{logical_map_json}

Concept index:
{concept_index_json}

Pattern analysis:
{patterns_json}

Build a model covering:
1. Ontology: What exists, what is real, how reality is structured
2. Epistemology: How knowledge works, what counts as evidence
3. Moral framework: Ethical positions, value hierarchy
4. Emotional philosophy: Role of emotion in thought/argument
5. Logical style: Deductive, inductive, dialectical, phenomenological, etc.
6. Recurring structural pattern: How arguments are typically built
7. Core tensions: Unresolved internal conflicts

Return JSON:
{{
  "ontology": {{"description": "...", "evidence": [{{"paragraph_id": "...", "quote": "..."}}]}},
  "epistemology": {{"description": "...", "evidence": [...]}},
  "moral_framework": {{"description": "...", "evidence": [...]}},
  "emotional_philosophy": {{"description": "...", "evidence": [...]}},
  "logical_style": {{"description": "...", "evidence": [...]}},
  "recurring_pattern": {{"description": "...", "evidence": [...]}},
  "core_tensions": [
    {{"tension": "...", "evidence": [...]}}
  ]
}}

Return ONLY the JSON. No explanation.
"""

# ── Skill 6: Cross-Book Synthesizer ──

CROSS_BOOK_SYSTEM = """\
You are a cross-book synthesizer for philosophical texts. You compare books by \
their concept definitions, ontology, epistemology, moral framework, logical style, \
and structural patterns.

Rules:
- Always cite sources as: Book_Folder_Name -> paragraph ID.
- Compare actual content, not surface similarity.
- Mark hypotheses with [HYPOTHESIS].
- Return valid JSON only.
"""

CROSS_BOOK_USER = """\
Given the following analyses of multiple books, perform a cross-book synthesis.

Books:
{books_json}

Question/Focus: {question}

Compare the books across these dimensions:
1. Concept definitions: How do the same or similar concepts differ?
2. Ontology: What each author takes to be real
3. Epistemology: How each author understands knowledge
4. Moral framework: Ethical positions and value hierarchies
5. Logical style: Deductive vs inductive vs dialectical etc.
6. Structural patterns: How arguments are built

Return JSON:
{{
  "comparisons": [
    {{
      "dimension": "concept_definitions|ontology|epistemology|moral_framework|logical_style|structural_patterns",
      "description": "...",
      "per_book": [
        {{"book_folder": "...", "position": "...", "evidence": "..."}}
      ],
      "synthesis": "...",
      "tensions": ["..."],
      "is_hypothesis": true/false
    }}
  ],
  "cross_links": [
    {{
      "concept": "...",
      "books": ["book_folder_1", "book_folder_2"],
      "relationship": "agreement|tension|evolution|contradiction",
      "description": "..."
    }}
  ],
  "overall_synthesis": "..."
}}

Return ONLY the JSON. No explanation.
"""

# ── Single Book Query ──

SINGLE_BOOK_QUERY_SYSTEM = """\
You are a philosophical knowledge retrieval engine. Given structural analysis of a \
book, you answer questions by reconstructing logical chains from the extracted data.

Rules:
- Include paragraph IDs for every claim.
- Include full verbatim quotes as evidence.
- Reconstruct the logical chain, not just point to paragraphs.
- Mark inferences with [INFERENCE].
- Return valid JSON only.
"""

SINGLE_BOOK_QUERY_USER = """\
Based on the following analysis of "{book_title}" by {author}, answer this question:

**Question:** {question}

Raw structure (relevant excerpts):
{raw_structure}

Logical map:
{logical_map}

Concept index:
{concept_index}

Return JSON:
{{
  "answer": "...",
  "paragraph_ids_used": ["..."],
  "verbatim_quotes": [
    {{"paragraph_id": "...", "quote": "..."}}
  ],
  "logical_chain": [
    {{"step": 1, "claim": "...", "paragraph_id": "...", "is_inference": false}}
  ],
  "confidence": "high|medium|low",
  "notes": "..."
}}

Return ONLY the JSON. No explanation.
"""
