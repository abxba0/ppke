# PPKE v2.0 Refactoring Checklist

**Generated**: 2026-02-22

Track progress through all 4 phases of the PPKE v2.0 refactoring.

---

## Phase 1: Audit & Specification ✅

### Audit Tasks
- [x] Audit `ppke/llm/prompts.py` for philosophy coupling
- [x] Audit `ppke/parser/models.py` for dataclass limitations
- [x] Audit `ppke/pipeline/orchestrator.py` for hardcoded pipeline
- [x] Audit `ppke/output/writer.py` for output structure

### Documentation Tasks
- [x] Create `spec-plan-v2.md`
- [x] Create `LICENSE` (Apache 2.0)
- [x] Create `REFACTORING_CHECKLIST.md` (this file)

### Validation
- [x] All philosophy couplings identified
- [x] Spec plan created
- [x] License added

**Status**: COMPLETE ✅

---

## Phase 2: Refactor Core 🔄

### Data Model Refactoring
- [ ] Convert `Paragraph` dataclass to Pydantic model
- [ ] Convert `Chapter` dataclass to Pydantic model
- [ ] Convert `Book` dataclass to Pydantic model
- [ ] Convert `ExtractionResult` to `BaseExtraction` Pydantic model
- [ ] Create `ppke/parser/schema_builder.py`
- [ ] Test dynamic Pydantic model generation

### Template System
- [ ] Create `ppke/templates/base.py`
- [ ] Create `ppke/templates/loader.py`
- [ ] Create `ppke/templates/validator.py`
- [ ] Create philosophy template files (4 YAML files)
- [ ] Create legal template files (4 YAML files)

### Pipeline Refactoring
- [ ] Refactor `ppke/pipeline/orchestrator.py` for dynamic stages
- [ ] Refactor `ppke/llm/prompts.py` for template loading
- [ ] Test philosophy pipeline (must match v1.x)
- [ ] Test legal pipeline

### CLI Updates
- [ ] Add `--domain` flag to `ppke ingest`
- [ ] Add `ppke list-domains` command
- [ ] Update help text

### Testing
- [ ] All existing tests pass
- [ ] Create `tests/test_templates.py`
- [ ] Create `tests/test_pydantic_models.py`

**Status**: PENDING ⏳

---

## Phase 3: Plugin Ecosystem 🔄

### Plugin Discovery
- [ ] Implement `discover_templates()`
- [ ] Scan official templates
- [ ] Scan custom templates (~/.ppke/plugins/)
- [ ] Handle name conflicts

### Plugin Validation
- [ ] Create `validate_template()` function
- [ ] Security checks
- [ ] Schema validation

### Documentation
- [ ] Create `PLUGINS.md`
- [ ] Create `TEMPLATE_DEVELOPMENT_GUIDE.md`
- [ ] Create example plugin (scientific_research)

### CLI Commands
- [ ] Implement `ppke validate-plugin`
- [ ] Implement `ppke promote-plugin`

**Status**: PENDING ⏳

---

## Phase 4: System Validation 🔄

### Testing
- [ ] Philosophy domain = v1.x (100% identical)
- [ ] Legal domain works
- [ ] Custom plugin works
- [ ] All 5 LLM providers work
- [ ] Test coverage >80%

### Performance
- [ ] Benchmark vs v1.x
- [ ] Memory usage acceptable
- [ ] Template loading <100ms

### Security
- [ ] Plugin validation blocks malicious code
- [ ] API keys not exposed
- [ ] Path traversal protected

### Documentation
- [ ] Create `MIGRATION_GUIDE.md`
- [ ] Update `CHANGELOG.md`
- [ ] Update `README.md`

**Status**: PENDING ⏳

---

## Release Checklist

- [ ] All phases complete
- [ ] Version bumped to 2.0.0
- [ ] Git tag: v2.0.0
- [ ] PyPI upload
- [ ] Announcement

---

**Last Updated**: 2026-02-22 02:08:55
