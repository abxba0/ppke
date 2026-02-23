# Contributing to PPKE

**Welcome!** 🎉 Thank you for considering contributing to the Personal Philosophical Knowledge Engine (PPKE). This document provides guidelines for contributing to the project.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [How Can I Contribute?](#how-can-i-contribute)
3. [Development Setup](#development-setup)
4. [Coding Standards](#coding-standards)
5. [Testing Requirements](#testing-requirements)
6. [Documentation Standards](#documentation-standards)
7. [Pull Request Process](#pull-request-process)
8. [Commit Message Guidelines](#commit-message-guidelines)
9. [Issue Reporting](#issue-reporting)
10. [Community](#community)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of experience level, gender identity, sexual orientation, disability, personal appearance, race, ethnicity, age, religion, or nationality.

### Expected Behavior

- ✅ Be respectful and inclusive
- ✅ Welcome newcomers and help them get started
- ✅ Accept constructive criticism gracefully
- ✅ Focus on what is best for the community
- ✅ Show empathy towards other community members

### Unacceptable Behavior

- ❌ Harassment, trolling, or discriminatory comments
- ❌ Personal or political attacks
- ❌ Publishing others' private information
- ❌ Other conduct inappropriate in a professional setting

### Enforcement

Violations may be reported to ppke-conduct@example.com. All complaints will be reviewed and investigated confidentially.

---

## How Can I Contribute?

### 1. Reporting Bugs

**Before Submitting:**
- Check existing issues to avoid duplicates
- Try to reproduce the bug with the latest version
- Gather relevant information (OS, Python version, PPKE version)

**Submit a Bug Report:**
1. Go to https://github.com/ppke/ppke/issues/new
2. Use the "Bug Report" template
3. Provide:
   - Clear title (e.g., "Template loading fails on Windows")
   - Steps to reproduce
   - Expected vs. actual behavior
   - Environment details
   - Relevant logs or screenshots

### 2. Suggesting Enhancements

**Feature Requests:**
1. Use the "Feature Request" template
2. Describe the problem you're trying to solve
3. Explain your proposed solution
4. Consider alternatives and trade-offs

**Template Requests:**
1. Use the "New Template" template
2. Describe the domain and use cases
3. Provide example documents
4. Offer to help implement (if possible)

### 3. Improving Documentation

Documentation improvements are always welcome!

**Areas to Contribute:**
- Fix typos or clarify confusing sections
- Add examples or tutorials
- Translate documentation
- Improve API documentation
- Create video tutorials

**Process:**
- Small fixes: Direct PR to `docs/` directory
- Large changes: Open issue first to discuss

### 4. Contributing Code

**Good First Issues:**
Look for issues labeled `good first issue` or `help wanted`

**High-Impact Areas:**
- New domain templates (Legal, Scientific, Medical)
- Performance optimizations
- Test coverage improvements
- CLI enhancements
- Obsidian integration

### 5. Creating Templates

See [TEMPLATE_DEVELOPMENT_GUIDE.md](./TEMPLATE_DEVELOPMENT_GUIDE.md) for detailed instructions.

**Template Contribution Process:**
1. Develop template locally
2. Test thoroughly (see testing requirements)
3. Publish to GitHub
4. Submit to community directory
5. (Optional) Request Tier 1 promotion

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- Virtual environment tool (venv, virtualenv, or conda)

### Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork

git clone https://github.com/YOUR-USERNAME/ppke.git
cd ppke

# Add upstream remote
git remote add upstream https://github.com/ppke/ppke.git
```

### Create Development Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Unix/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"
```

### Install Development Tools

```bash
# Linters and formatters
pip install black ruff mypy

# Testing tools
pip install pytest pytest-cov pytest-asyncio

# Documentation tools
pip install mkdocs mkdocs-material
```

### Verify Setup

```bash
# Run tests
pytest

# Check code style
ruff check .

# Type check
mypy ppke/

# Format code
black .
```

---

## Coding Standards

### Python Style Guide

We follow **PEP 8** with some modifications:

**Key Rules:**
- Line length: 100 characters (not 79)
- Use `black` for formatting (run before committing)
- Use type hints for all function signatures
- Docstrings for all public classes and methods (Google style)

### Code Formatting

**Use Black:**
```bash
# Format all files
black .

# Check without changing
black --check .
```

**Configuration (pyproject.toml):**
```toml
[tool.black]
line-length = 100
target-version = ['py310']
```

### Linting

**Use Ruff:**
```bash
# Check for issues
ruff check .

# Auto-fix where possible
ruff check --fix .
```

**Configuration (pyproject.toml):**
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N"]
ignore = ["E501"]  # Line too long (handled by black)
```

### Type Hints

**Required for all public APIs:**
```python
# Good
def process_paragraph(text: str, max_length: int = 500) -> dict[str, Any]:
    """Process a paragraph and extract key information."""
    ...

# Bad (missing types)
def process_paragraph(text, max_length=500):
    ...
```

**Type Checking:**
```bash
# Run mypy
mypy ppke/

# Configuration in pyproject.toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### Docstring Format

**Use Google-style docstrings:**
```python
def extract_concepts(paragraphs: list[str], model: str = "gpt-4") -> list[dict]:
    """Extract concepts from a list of paragraphs.

    This function uses an LLM to identify key concepts and their
    relationships across multiple paragraphs.

    Args:
        paragraphs: List of paragraph texts to analyze.
        model: LLM model to use (default: "gpt-4").

    Returns:
        List of concept dictionaries, each containing:
            - name (str): Concept name
            - definition (str): Concept definition
            - occurrences (list[int]): Paragraph indices

    Raises:
        ValueError: If paragraphs list is empty.
        LLMError: If LLM API call fails.

    Example:
        >>> paragraphs = ["Dasein is being-there...", "Heidegger explores..."]
        >>> concepts = extract_concepts(paragraphs)
        >>> print(concepts[0]['name'])
        'Dasein'
    """
    if not paragraphs:
        raise ValueError("Paragraphs list cannot be empty")
    ...
```

### Import Organization

**Use isort (integrated with ruff):**
```python
# Standard library
import json
import os
from pathlib import Path
from typing import Any

# Third-party
import pydantic
from anthropic import Anthropic

# Local
from ppke.config import PPKEConfig
from ppke.templates.base import DomainTemplate
```

---

## Testing Requirements

### Test Coverage

**Minimum Requirements:**
- Unit tests: >90% coverage for new code
- Integration tests: Cover major workflows
- Template tests: All 7 skills tested

### Writing Tests

**Use pytest:**
```python
# tests/test_extraction.py

import pytest
from ppke.pipeline.extractor import Extractor
from ppke.parser.models import Paragraph

@pytest.fixture
def sample_paragraph():
    """Sample paragraph for testing."""
    return Paragraph(
        id="{01}.p1.0",
        chapter_number=1,
        paragraph_number=1,
        sub_paragraph=0,
        text="Dasein is Heidegger's term for human existence.",
        token_count=12,
    )

def test_extraction_schema(sample_paragraph):
    """Test extraction returns valid schema."""
    extractor = Extractor(template="philosophy")
    result = extractor.extract(sample_paragraph)

    assert result.paragraph_id == "{01}.p1.0"
    assert len(result.summary) > 0
    assert "Dasein" in result.key_terms

def test_extraction_empty_paragraph():
    """Test extraction handles empty paragraphs."""
    paragraph = Paragraph(id="{01}.p1.0", text="", ...)

    extractor = Extractor(template="philosophy")
    with pytest.raises(ValueError, match="empty"):
        extractor.extract(paragraph)
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ppke --cov-report=html

# Run specific test file
pytest tests/test_extraction.py

# Run specific test
pytest tests/test_extraction.py::test_extraction_schema

# Run tests matching pattern
pytest -k "extraction"

# Run slow tests (integration with LLM)
pytest -m slow

# Skip slow tests
pytest -m "not slow"
```

### Test Markers

```python
# Mark slow tests (requires LLM API)
@pytest.mark.slow
def test_with_real_llm():
    ...

# Mark tests requiring API keys
@pytest.mark.requires_api
def test_anthropic_integration():
    ...

# Mark integration tests
@pytest.mark.integration
def test_full_pipeline():
    ...
```

---

## Documentation Standards

### Code Documentation

**All public APIs must be documented:**
- Classes: Purpose, attributes, example usage
- Functions: Args, returns, raises, example
- Modules: Overview, key components

### README Updates

When adding features, update:
- Installation instructions (if needed)
- Usage examples
- Command reference
- FAQ

### Changelog

**Update CHANGELOG.md for all user-facing changes:**
```markdown
## [Unreleased]

### Added
- New template for legal document analysis (#123)
- CLI command `ppke template validate` (#145)

### Changed
- Improved error messages for template loading (#134)

### Fixed
- Template discovery on Windows (#142)
```

**Versioning:**
- **MAJOR:** Breaking changes
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes

---

## Pull Request Process

### Before Submitting

1. ✅ Run tests: `pytest`
2. ✅ Check coverage: `pytest --cov`
3. ✅ Format code: `black .`
4. ✅ Lint: `ruff check .`
5. ✅ Type check: `mypy ppke/`
6. ✅ Update documentation
7. ✅ Update CHANGELOG.md

### Creating a Pull Request

1. **Create a branch:**
   ```bash
   git checkout -b feature/template-legal
   ```

2. **Make changes:**
   - Write code
   - Add tests
   - Update docs

3. **Commit changes:**
   ```bash
   git add .
   git commit -m "feat: add legal template for contract analysis"
   ```

4. **Push to your fork:**
   ```bash
   git push origin feature/template-legal
   ```

5. **Open PR on GitHub:**
   - Use the PR template
   - Link related issues
   - Provide clear description

### PR Template

```markdown
## Description
Brief description of changes.

## Related Issues
Closes #123

## Type of Change
- [ ] Bug fix
- [x] New feature
- [ ] Breaking change
- [ ] Documentation update

## Checklist
- [x] Tests pass locally
- [x] Added tests for new functionality
- [x] Updated documentation
- [x] Updated CHANGELOG.md
- [x] Code follows style guidelines
```

### Review Process

1. **Automated Checks:**
   - CI runs tests on all Python versions (3.10, 3.11, 3.12)
   - Linting and type checking
   - Coverage report

2. **Code Review:**
   - At least 1 maintainer approval required
   - Reviewers may request changes

3. **Merge:**
   - Squash and merge (clean history)
   - Delete branch after merge

---

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat:** New feature
- **fix:** Bug fix
- **docs:** Documentation changes
- **style:** Code style (formatting, no logic changes)
- **refactor:** Code refactoring
- **test:** Adding or updating tests
- **chore:** Build process, dependencies, etc.

### Examples

```bash
# Feature
git commit -m "feat(templates): add legal template for contract analysis"

# Bug fix
git commit -m "fix(parser): handle empty paragraphs correctly"

# Documentation
git commit -m "docs: update template development guide"

# Breaking change
git commit -m "feat(api)!: change template interface to use Pydantic

BREAKING CHANGE: Templates must now return Pydantic models instead of dicts."
```

---

## Issue Reporting

### Bug Reports

**Include:**
- PPKE version: `ppke --version`
- Python version: `python --version`
- Operating system
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs or error messages

### Feature Requests

**Include:**
- Problem you're trying to solve
- Proposed solution
- Alternatives considered
- Example use cases

### Template Requests

**Include:**
- Domain description
- Example documents
- Specific analysis requirements
- Offer to contribute implementation

---

## Community

### Communication Channels

- **GitHub Issues:** Bug reports, feature requests
- **GitHub Discussions:** General questions, ideas, showcase
- **Discord:** Real-time chat (https://discord.gg/ppke)
- **Email:** ppke-dev@example.com

### Getting Help

- **Documentation:** https://ppke.readthedocs.io
- **Wiki:** https://github.com/ppke/ppke/wiki
- **FAQ:** https://github.com/ppke/ppke/wiki/FAQ
- **Examples:** https://github.com/ppke/ppke-examples

### Recognition

Contributors are recognized in:
- CHANGELOG.md (all contributors)
- README.md (significant contributions)
- GitHub contributors graph
- Special mentions in release notes

---

## License

By contributing to PPKE, you agree that your contributions will be licensed under the Apache License 2.0. See [LICENSE](./LICENSE) for details.

---

## Questions?

If you have questions about contributing, please:
1. Check the [FAQ](https://github.com/ppke/ppke/wiki/FAQ)
2. Search existing [issues](https://github.com/ppke/ppke/issues) and [discussions](https://github.com/ppke/ppke/discussions)
3. Open a new discussion in the "Q&A" category

**Thank you for contributing to PPKE!** 🎉

---

**Document Version:** 1.0
**Last Updated:** 2026-02-21
**Maintained By:** PPKE Core Team
