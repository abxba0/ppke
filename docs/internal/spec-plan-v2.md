# PPKE v2.0 Refactoring Specification
**From Philosophy-Specific Tool → General-Purpose Knowledge Framework**

**Generated**: 2026-02-22 02:08:55

---

## Executive Summary

This specification outlines the transition of PPKE from a philosophy-specific text analyzer to a domain-agnostic knowledge engine with plugin architecture.

---

## Audit Summary

### 1. Prompts Audit (ppke/llm/prompts.py)

**Status**: CRITICAL

- **Prompt Templates Found**: 8
- **Prompt Names**: STRUCTURAL_EXTRACTION_SYSTEM, LOGICAL_MAP_SYSTEM, CONCEPT_INDEX_SYSTEM, PATTERN_DETECTION_SYSTEM, AUTHOR_MODEL_SYSTEM, CROSS_BOOK_SYSTEM, SINGLE_BOOK_QUERY_SYSTEM, CONCEPT_DEDUP_SYSTEM
- **Philosophy Terms**: {'philosophical text': 7, 'thesis': 10, 'argument': 13, 'premise': 2, 'claim': 12}

**Refactoring Strategy**:
- Extract all prompts to `ppke/templates/official/philosophy/prompts.yml`
- Create dynamic prompt loader in `ppke/llm/prompts.py`
- Replace hardcoded strings with template references

---

### 2. Data Models Audit (ppke/parser/models.py)

**Status**: MODERATE

- **Dataclasses Found**: 8
- **Dataclass Names**: Paragraph, Chapter, Book, ExtractionResult, ConceptEntry, LogicalNode, PatternEntry, CoverageReport
- **Philosophy Fields**: {'function_in_argument': 1, 'explicit_claims': 1, 'implicit_assumptions': 1, 'logical_steps': 1}

**Refactoring Strategy**:
- Convert all dataclasses to Pydantic `BaseModel`
- Create `BaseExtraction` with core fields
- Implement dynamic model builder: `ppke/parser/schema_builder.py`
- Templates define domain-specific fields in `schema.yml`

---

### 3. Pipeline Audit

**Status**: CRITICAL

- **Files Audited**: 4
- **Findings**: 2 issues

**Key Issues**:
- `orchestrator.py`: Hardcoded logical_map stage (CRITICAL)
- `logical_map.py`: Hardcoded logical_map stage (CRITICAL)

**Refactoring Strategy**:
- Replace hardcoded 7-stage pipeline with dynamic loading
- Each template defines its own stages in `template.yml`
- Create generic `ppke/pipeline/stages/analyzer.py`
- Philosophy template uses exact v1.x pipeline

---

### 4. Output Generation Audit

**Status**: {self.audit_results['output'].get('severity', 'UNKNOWN')}

- **Hardcoded Files**: {self.audit_results['output'].get('hardcoded_files', [])}

**Refactoring Strategy**:
- Templates define output files in `outputs.yml`
- Create Jinja2-based renderer in `ppke/output/renderers.py`
- Support custom output formats per domain

---

## Architecture Changes

### Template System Design

```
ppke/templates/
├── base.py           # PluginTemplate base class
├── loader.py         # Template discovery & loading
├── validator.py      # Security & schema validation
│
├── official/         # Tier 1: Official plugins
│   ├── philosophy/
│   │   ├── template.yml
│   │   ├── schema.yml
│   │   ├── prompts.yml
│   │   └── outputs.yml
│   └── legal/
│       └── ...
│
└── custom/           # Pointer to ~/.ppke/plugins/
```

---

## Implementation Plan

### Phase 2: Refactor Core (20-30 hours)
- [ ] Convert dataclasses to Pydantic
- [ ] Create schema builder
- [ ] Build template system
- [ ] Create philosophy template
- [ ] Create legal template
- [ ] Refactor pipeline
- [ ] Update CLI

### Phase 3: Plugin Ecosystem (12-16 hours)
- [ ] Plugin discovery
- [ ] Plugin validation
- [ ] Documentation (PLUGINS.md)
- [ ] Example custom plugin

### Phase 4: System Validation (16-20 hours)
- [ ] Backward compatibility testing
- [ ] Multi-domain validation
- [ ] Performance benchmarking
- [ ] Security audit
- [ ] Migration guide

---

## Success Criteria

✅ 100% backward compatibility with philosophy domain
✅ At least 2 working domains (philosophy + legal)
✅ Template system with validation
✅ Dynamic Pydantic model generation
✅ Apache 2.0 license applied
✅ Test coverage >80%

---

**For detailed implementation steps, see**: `prompts/phase-2-refactor-core.md`
