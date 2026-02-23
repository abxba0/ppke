# PPKE v2.0 Refactoring Metaprompts
**Complete AI-Assisted Transition from Philosophy-Specific to Multi-Domain Knowledge Framework**

---

## 📋 Overview

This directory contains **4 comprehensive metaprompts** designed to guide the refactoring of PPKE from a philosophy-specific tool to a general-purpose knowledge engine with plugin architecture.

Each metaprompt is **AI assistant-ready** - you can copy the entire file and paste it into Claude, GPT-4, or another LLM to execute the phase autonomously.

---

## 🎯 The 4 Phases

| Phase | File | Effort | Complexity | Prerequisites |
|-------|------|--------|------------|---------------|
| **1. Audit & Specification** | `phase-1-audit-specification.md` | 8-12 hours | Medium | None |
| **2. Refactor Core** | `phase-2-refactor-core.md` | 20-30 hours | High | Phase 1 complete |
| **3. Plugin Ecosystem** | `phase-3-plugin-ecosystem.md` | 12-16 hours | Medium | Phases 1-2 complete |
| **4. System Validation** | `phase-4-system-validation.md` | 16-20 hours | Medium-High | Phases 1-3 complete |

**Total Estimated Effort**: 56-78 hours

---

## 📚 Phase Summaries

### **Phase 1: Audit & Specification** 🔍
**File**: `phase-1-audit-specification.md` (1,000+ lines)

**What It Does**:
- Audits all philosophy coupling in `ppke/llm/prompts.py`, `ppke/parser/models.py`, `ppke/pipeline/*.py`
- Documents every hardcoded assumption
- Creates comprehensive `spec-plan-v2.md` with refactoring design
- Adds Apache 2.0 `LICENSE` file
- Creates `REFACTORING_CHECKLIST.md` for tracking

**Deliverables**:
- ✅ `spec-plan-v2.md` (detailed architecture design)
- ✅ `LICENSE` (Apache 2.0)
- ✅ `REFACTORING_CHECKLIST.md` (migration tracker)
- ✅ Audit report of all philosophy couplings

**Key Sections**:
1. Audit `ppke/llm/prompts.py` (7+ hardcoded prompts)
2. Audit `ppke/parser/models.py` (philosophy-specific dataclasses)
3. Audit `ppke/pipeline/orchestrator.py` (hardcoded 7-stage pipeline)
4. Audit `ppke/output/writer.py` (philosophy output structure)
5. Create specification document with Pydantic strategy

---

### **Phase 2: Refactor Core** ⚙️
**File**: `phase-2-refactor-core.md` (900+ lines)

**What It Does**:
- Converts dataclasses to Pydantic models
- Creates dynamic schema builder (`ppke/parser/schema_builder.py`)
- Implements template system (`ppke/templates/base.py`, `loader.py`, `validator.py`)
- Creates philosophy template (100% v1.x compatible)
- Creates legal template (new domain)
- Refactors pipeline for dynamic stage loading
- Updates CLI with `--domain` flag

**Deliverables**:
- ✅ Pydantic models in `ppke/parser/models.py`
- ✅ `ppke/parser/schema_builder.py` (dynamic model generator)
- ✅ `ppke/templates/official/philosophy/` (backward compatible)
- ✅ `ppke/templates/official/legal/` (new domain)
- ✅ Refactored `ppke/pipeline/orchestrator.py`
- ✅ Refactored `ppke/llm/prompts.py` (dynamic loader)
- ✅ Updated `ppke/cli.py` with `--domain` flag

**Key Transformations**:
```python
# BEFORE (v1.x)
@dataclass
class ExtractionResult:
    function_in_argument: str  # Hardcoded philosophy field

# AFTER (v2.0)
class BaseExtraction(BaseModel):
    # Generic fields only
    # Domain-specific fields defined in templates
```

---

### **Phase 3: Plugin Ecosystem** 🔌
**File**: `phase-3-plugin-ecosystem.md` (700+ lines)

**What It Does**:
- Implements 2-tier plugin system (Official + Custom)
- Creates plugin discovery (scans `~/.ppke/plugins/`)
- Creates complete plugin development documentation
- Builds example Tier 2 plugin (scientific_research)
- Implements CLI commands for plugin management

**Deliverables**:
- ✅ `PLUGINS.md` (plugin development guide for users)
- ✅ `TEMPLATE_DEVELOPMENT_GUIDE.md` (technical reference)
- ✅ `~/.ppke/plugins/scientific_research/` (example plugin)
- ✅ `ppke/templates/registry.py` (plugin registry)
- ✅ CLI: `ppke list-domains`, `ppke validate-plugin`, `ppke promote-plugin`

**Plugin Structure**:
```
~/.ppke/plugins/my_domain/
├── template.yml     # Config & stages
├── schema.yml       # Pydantic field definitions
├── prompts.yml      # LLM prompts
└── outputs.yml      # Output templates
```

---

### **Phase 4: System Validation** ✅
**File**: `phase-4-system-validation.md` (650+ lines)

**What It Does**:
- Comprehensive backward compatibility testing
- Multi-domain validation (philosophy, legal, custom)
- Performance benchmarking (vs. v1.x baseline)
- Security auditing (plugin validation, API key safety)
- Integration testing (vector search, knowledge graph)
- Documentation updates (migration guide, changelog)

**Deliverables**:
- ✅ Test suite passing (>80% coverage)
- ✅ Backward compatibility report (philosophy = v1.x)
- ✅ Performance benchmarks documented
- ✅ Security audit report (zero vulnerabilities)
- ✅ `MIGRATION_GUIDE.md` (v1.x → v2.0)
- ✅ `CHANGELOG.md` (release notes)
- ✅ Updated `README.md` with multi-domain examples

**Test Matrix**:
| Domain | Anthropic | OpenAI | DeepSeek | Gemini | OpenRouter |
|--------|-----------|--------|----------|--------|------------|
| Philosophy | ✅ | ✅ | ✅ | ✅ | ✅ |
| Legal | ✅ | ✅ | ✅ | ✅ | ✅ |
| Scientific | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 🚀 Quick Start

### **Option 1: Automated Execution (Recommended)**

Use the quick-start script to automate Phase 1:

```bash
# Check prerequisites
python prompts/verify-prerequisites.py

# Run Phase 1 audit
python prompts/quick-start-phase-1.py

# Track progress
python prompts/progress-tracker.py
```

---

### **Option 2: Manual AI-Assisted Execution**

1. **Open your AI assistant** (Claude, GPT-4, etc.)

2. **Phase 1**:
   ```
   Copy: prompts/phase-1-audit-specification.md
   Paste into AI assistant
   AI will audit codebase and create spec-plan-v2.md
   ```

3. **Phase 2**:
   ```
   Copy: prompts/phase-2-refactor-core.md
   Paste into AI assistant
   AI will refactor core codebase
   Validate: ppke ingest --domain philosophy test.md
   ```

4. **Phase 3**:
   ```
   Copy: prompts/phase-3-plugin-ecosystem.md
   Paste into AI assistant
   AI will create plugin system
   Validate: ppke list-domains
   ```

5. **Phase 4**:
   ```
   Copy: prompts/phase-4-system-validation.md
   Paste into AI assistant
   AI will run comprehensive tests
   Validate: pytest tests/ --cov=ppke
   ```

---

### **Option 3: Shell Script Wrapper**

```bash
# Run entire refactoring sequentially
./prompts/run-phase.sh 1  # Phase 1
./prompts/run-phase.sh 2  # Phase 2 (after Phase 1 complete)
./prompts/run-phase.sh 3  # Phase 3
./prompts/run-phase.sh 4  # Phase 4

# Or run all phases (use with caution!)
./prompts/run-phase.sh all
```

---

## 🔄 Ralph Wiggum Methodology

Every phase follows the **Execute → Audit → Iterate → Validate** cycle:

```
1. EXECUTE  → Implement the change/task
2. AUDIT    → Check for logical, functional, integration errors
3. ITERATE  → Fix issues until specification compliance
4. VALIDATE → Test in real-world scenarios
```

This methodology is integrated into every task within each metaprompt.

---

## 📊 Progress Tracking

### **Automated Progress Tracker**

```bash
python prompts/progress-tracker.py
```

**Output**:
```
PPKE v2.0 Refactoring Progress

Phase 1: Audit & Specification         [████████████████████] 100% ✅
Phase 2: Refactor Core                 [██████████          ]  50% 🔄
Phase 3: Plugin Ecosystem              [                    ]   0% ⏳
Phase 4: System Validation             [                    ]   0% ⏳

Overall Progress: 37.5% (30/80 tasks complete)

Next Task: Convert Chapter dataclass to Pydantic model
```

---

### **Manual Tracking**

Use `REFACTORING_CHECKLIST.md` (created in Phase 1):
- [ ] Phase 1 tasks (7 items)
- [ ] Phase 2 tasks (30+ items)
- [ ] Phase 3 tasks (18+ items)
- [ ] Phase 4 tasks (25+ items)

---

## 🛠️ Helpful Scripts

All scripts are in the `prompts/` directory:

| Script | Purpose |
|--------|---------|
| `verify-prerequisites.py` | Check if system is ready for refactoring |
| `quick-start-phase-1.py` | Automate Phase 1 audit and spec creation |
| `progress-tracker.py` | Track completion across all 4 phases |
| `run-phase.sh` | Shell wrapper for running phases sequentially |

---

## 📦 What Gets Created

### **Phase 1 Outputs**
```
ppke/
├── spec-plan-v2.md              # Architecture design (NEW)
├── LICENSE                       # Apache 2.0 (NEW)
└── REFACTORING_CHECKLIST.md     # Migration tracker (NEW)
```

### **Phase 2 Outputs**
```
ppke/
├── parser/
│   ├── models.py                 # Pydantic models (REFACTORED)
│   └── schema_builder.py         # Dynamic model builder (NEW)
├── templates/
│   ├── base.py                   # PluginTemplate class (NEW)
│   ├── loader.py                 # Template discovery (NEW)
│   ├── validator.py              # Schema validation (NEW)
│   └── official/
│       ├── philosophy/           # Philosophy template (NEW)
│       │   ├── template.yml
│       │   ├── schema.yml
│       │   ├── prompts.yml
│       │   └── outputs.yml
│       └── legal/                # Legal template (NEW)
│           └── ...
├── llm/
│   └── prompts.py                # Dynamic loader (REFACTORED)
└── pipeline/
    └── orchestrator.py           # Dynamic stages (REFACTORED)
```

### **Phase 3 Outputs**
```
ppke/
├── PLUGINS.md                    # User guide (NEW)
├── TEMPLATE_DEVELOPMENT_GUIDE.md # Technical reference (NEW)
└── ppke/
    └── templates/
        └── registry.py           # Plugin registry (NEW)

~/.ppke/
└── plugins/
    └── scientific_research/      # Example plugin (NEW)
        ├── template.yml
        ├── schema.yml
        ├── prompts.yml
        └── outputs.yml
```

### **Phase 4 Outputs**
```
ppke/
├── MIGRATION_GUIDE.md            # v1.x → v2.0 guide (NEW)
├── CHANGELOG.md                  # Release notes (UPDATED)
├── README.md                     # Multi-domain examples (UPDATED)
└── tests/
    ├── test_template_system.py   # Template tests (NEW)
    ├── test_backward_compatibility.py # v1.x compat tests (NEW)
    └── ...
```

---

## ✅ Success Criteria

### **Phase 1**
- [ ] All philosophy couplings identified and documented
- [ ] `spec-plan-v2.md` complete with Pydantic refactoring strategy
- [ ] Apache 2.0 `LICENSE` created

### **Phase 2**
- [ ] `ppke ingest philosophy.md` produces identical output to v1.x
- [ ] `ppke ingest --domain legal contract.md` successfully ingests
- [ ] All existing tests pass

### **Phase 3**
- [ ] `ppke list-domains` shows philosophy, legal, scientific_research
- [ ] `ppke validate-plugin` rejects invalid plugins
- [ ] Example custom plugin works

### **Phase 4**
- [ ] 100% backward compatibility with philosophy domain
- [ ] Test coverage >80%
- [ ] All 5 LLM providers work with all 3 domains
- [ ] Zero security vulnerabilities
- [ ] Performance ≥90% of v1.x

---

## 🔒 Security Notes

The metaprompts include security validation for:
- ✅ Plugin code injection prevention
- ✅ Path traversal protection
- ✅ API key safety (not exposed in templates)
- ✅ Malicious prompt detection
- ✅ YAML injection protection

**Phase 3** implements security checks in `ppke/templates/validator.py`.

---

## 💡 Tips for Success

### **1. One Phase at a Time**
Don't skip phases. Each builds on the previous.

### **2. Test Frequently**
Run `pytest tests/` after every major change in Phase 2.

### **3. Backup Your Vault**
```bash
cp -r ~/KnowledgeBase ~/KnowledgeBase_backup
```

### **4. Use Git Branches**
```bash
git checkout -b refactor-phase-1
git checkout -b refactor-phase-2
# etc.
```

### **5. Validate Early**
After Phase 2, immediately test:
```bash
ppke ingest --domain philosophy test.md
diff <(cat v1_output.json) <(cat v2_output.json)
```

### **6. Document Issues**
Keep notes of deviations from metaprompts - they help in Phase 4 debugging.

---

## 📞 Getting Help

### **Issues During Execution**

1. **Phase 1**: If audit finds unexpected couplings
   - Review the "Common Issues" section in the metaprompt
   - Document new couplings in your audit report

2. **Phase 2**: If tests fail after refactoring
   - Check Phase 2 "Validation Criteria" section
   - Ensure Pydantic models match dataclass behavior exactly

3. **Phase 3**: If plugins don't load
   - Run `ppke validate-plugin <path>` for detailed errors
   - Check `ppke/templates/validator.py` for validation logic

4. **Phase 4**: If backward compatibility fails
   - Compare v1.x and v2.0 extractions line-by-line
   - Check philosophy template matches v1.x prompts exactly

---

## 🎓 Learning Resources

### **Pydantic** (used in Phase 2)
- Official Docs: https://docs.pydantic.dev/
- Dynamic Models: https://docs.pydantic.dev/latest/usage/models/#dynamic-model-creation

### **YAML** (used for templates)
- Specification: https://yaml.org/spec/
- Python YAML: https://pyyaml.org/wiki/PyYAMLDocumentation

### **Plugin Architectures**
- Python Plugins: https://realpython.com/python-application-layouts/
- Template Patterns: https://en.wikipedia.org/wiki/Template_method_pattern

---

## 📅 Example Timeline

**Experienced Developer** (full-time):
- Week 1: Phase 1 (2 days) + Phase 2 (3 days)
- Week 2: Phase 2 completion (2 days) + Phase 3 (3 days)
- Week 3: Phase 4 (3-4 days) + buffer for fixes

**Part-Time** (10 hours/week):
- Month 1: Phase 1 + start Phase 2
- Month 2: Complete Phase 2 + Phase 3
- Month 3: Phase 4 + release prep

---

## 🎉 Release Checklist

After completing all 4 phases:

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Test coverage >80%
- [ ] Documentation complete (README, PLUGINS.md, MIGRATION_GUIDE.md)
- [ ] Version bumped to 2.0.0 in `pyproject.toml`
- [ ] Git tag created: `git tag v2.0.0`
- [ ] CHANGELOG.md updated
- [ ] PyPI upload: `python -m build && twine upload dist/*`
- [ ] GitHub release published
- [ ] Community announcement

---

## 🤝 Contributing

If you improve these metaprompts:
1. Open a PR with your enhancements
2. Document what you changed and why
3. Test your changes by executing the phase

---

## 📜 License

These metaprompts are part of the PPKE project and follow the same license (Apache 2.0).

---

**Last Updated**: 2025-02-22
**Metaprompt Version**: 1.0
**Compatible with**: PPKE v1.9.x → v2.0 transition

---

**Questions?** Open a GitHub issue with the `refactoring` label.

**Ready to start?** Run `python prompts/verify-prerequisites.py` to check if your system is ready!
