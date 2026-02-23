# PPKE v2.0 Refactoring - Quick Start Guide

**Get started refactoring PPKE in 5 minutes**

---

## 🚀 Fastest Path to Phase 1

```bash
# 1. Verify prerequisites (30 seconds)
python prompts/verify-prerequisites.py

# 2. Run Phase 1 automation (2-5 minutes)
python prompts/quick-start-phase-1.py

# 3. Review generated files
ls -la spec-plan-v2.md LICENSE REFACTORING_CHECKLIST.md
```

**That's it!** You now have your refactoring specification ready.

---

## 📋 What Just Happened?

### Files Created:
- ✅ `spec-plan-v2.md` - Complete architecture design
- ✅ `LICENSE` - Apache 2.0 license
- ✅ `REFACTORING_CHECKLIST.md` - Migration tracker

### Audit Completed:
- ✅ Analyzed `ppke/llm/prompts.py` (hardcoded prompts)
- ✅ Analyzed `ppke/parser/models.py` (dataclasses)
- ✅ Analyzed `ppke/pipeline/*.py` (philosophy coupling)
- ✅ Analyzed `ppke/output/writer.py` (output structure)

---

## 🎯 Next Steps

### Option 1: Continue with Automation
```bash
# Check progress
python prompts/progress-tracker.py

# Move to Phase 2 (requires AI or manual work)
# Read: prompts/phase-2-refactor-core.md
```

### Option 2: Use AI Assistant
```
1. Copy prompts/phase-2-refactor-core.md
2. Paste into Claude/GPT-4
3. AI executes Phase 2 refactoring
4. Review changes and run tests
```

### Option 3: Manual Implementation
```
1. Read spec-plan-v2.md
2. Follow REFACTORING_CHECKLIST.md
3. Implement changes step-by-step
4. Track progress with progress-tracker.py
```

---

## 📊 Track Progress

```bash
# Simple progress view
python prompts/progress-tracker.py

# Detailed with task lists
python prompts/progress-tracker.py --detailed
```

**Example Output:**
```
PPKE v2.0 Refactoring Progress

Overall Progress:
  [████████████████████] 100.0% (6/6 tasks)

Phase 1: Audit & Specification         ✅
  [████████████████████] 100.0% (6/6)

Phase 2: Refactor Core                 ⏳
  [░░░░░░░░░░░░░░░░░░░░]   0.0% (0/9)

Next Task: Phase 2: Convert to Pydantic
```

---

## 🛠️ All Available Scripts

| Script | Purpose | Runtime |
|--------|---------|---------|
| `verify-prerequisites.py` | Check system readiness | 30 sec |
| `quick-start-phase-1.py` | Automate Phase 1 audit | 2-5 min |
| `progress-tracker.py` | Track completion status | 5 sec |
| `run-phase.sh` / `.bat` | Run phases sequentially | Varies |

---

## 🎓 Learning Path

### If You're New to PPKE:
1. Read `prompts/README.md` - Master index
2. Read `prompts/phase-1-audit-specification.md` - Understand coupling
3. Run `verify-prerequisites.py` - Check readiness
4. Run `quick-start-phase-1.py` - Generate spec

### If You're Experienced:
1. Run prerequisites check
2. Run Phase 1 automation
3. Copy Phase 2 metaprompt to AI assistant
4. Review AI changes, run tests
5. Repeat for Phases 3-4

---

## 💡 Tips

### Backup First
```bash
# Backup your vault
cp -r ~/KnowledgeBase ~/KnowledgeBase_backup

# Create git branch
git checkout -b refactor-v2
git add .
git commit -m "Pre-refactoring checkpoint"
```

### Test Frequently
```bash
# After Phase 2 changes
pytest tests/ -v

# After CLI changes
ppke ingest --domain philosophy test.md
```

### Use Progress Tracker
```bash
# After completing each task
python prompts/progress-tracker.py
```

---

## 🆘 Troubleshooting

### "Python version too old"
Install Python 3.10+: https://python.org

### "Pydantic not found"
```bash
pip install pydantic>=2.0
```

### "PPKE codebase not found"
Run from repository root:
```bash
cd /path/to/ppke
python prompts/quick-start-phase-1.py
```

### "Phase 1 script fails"
Run with verbose mode:
```bash
python prompts/quick-start-phase-1.py --verbose
```

---

## 📅 Estimated Timeline

| Phase | AI-Assisted | Manual | Part-Time (10h/week) |
|-------|-------------|--------|----------------------|
| Phase 1 | 5 min | 4-6 hours | 1 week |
| Phase 2 | 2-4 hours | 20-30 hours | 3-4 weeks |
| Phase 3 | 1-2 hours | 12-16 hours | 2 weeks |
| Phase 4 | 1-2 hours | 16-20 hours | 2-3 weeks |
| **Total** | **6-8 hours** | **56-78 hours** | **8-10 weeks** |

---

## ✅ Success Criteria

After Phase 1:
- [ ] `spec-plan-v2.md` exists and is detailed
- [ ] All philosophy couplings documented
- [ ] LICENSE file created (Apache 2.0)

After Phase 2:
- [ ] `ppke ingest philosophy.md` produces identical output to v1.x
- [ ] `ppke ingest --domain legal contract.md` works
- [ ] All existing tests pass

After Phase 3:
- [ ] `ppke list-domains` shows 3+ domains
- [ ] Custom plugin works
- [ ] `PLUGINS.md` complete

After Phase 4:
- [ ] 100% backward compatibility verified
- [ ] Test coverage >80%
- [ ] Zero security vulnerabilities
- [ ] Ready for v2.0 release

---

## 🎉 Ready to Start?

```bash
# Step 1: Verify
python prompts/verify-prerequisites.py

# Step 2: Launch Phase 1
python prompts/quick-start-phase-1.py

# Step 3: Review spec
cat spec-plan-v2.md

# Step 4: Proceed to Phase 2
# (Read prompts/phase-2-refactor-core.md)
```

---

**Questions?** Read the full documentation: `prompts/README.md`

**Stuck?** Check: `prompts/phase-<N>-*.md` for detailed instructions

**Want help?** Open GitHub issue with `refactoring` label
