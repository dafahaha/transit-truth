# Contributing to TransitTruth

Thank you for your interest in contributing to TransitTruth! This document outlines how to contribute to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/transit-truth.git`
3. Create a feature branch: `git checkout -b feature/your-feature`
4. Make your changes
5. Run tests: `cd backend && python -m pytest tests/ -v`
6. Commit and push: `git commit -m "Add your feature" && git push origin feature/your-feature`
7. Open a Pull Request

## Development Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

### CLI Usage

```bash
cd backend
python -m app.cli audit --api-key sk-xxx --base-url https://api.example.com/v1 --model gpt-4o
python -m app.cli list
python -m app.cli export --audit-id abc123 --output report.html
```

## How to Contribute

### Add New Probes

Probes are the core of TransitTruth's detection capability. To add a new probe:

1. Add the probe definition to `backend/app/core/probes.py`
2. If it's a new category, add the category to the probe lists
3. Add randomization logic to `backend/app/core/randomized_probes.py`
4. Add tests to `backend/tests/test_probes.py`
5. Update the methodology documentation

**Probe design principles:**
- Preserve the characteristic being measured while randomizing specific content
- Avoid fixed strings that relay services could whitelist
- Include expected token ranges for tokenizer probes
- Use appropriate temperature (high for behavioral, low for capability)

### Improve Detection Accuracy

- Add new model families to `backend/app/config.py`
- Improve the fingerprint analysis in `backend/app/core/fingerprint.py`
- Add benchmark data collection scripts
- Improve scoring algorithms in `backend/app/core/auditor.py`

### Fix Bugs

- Check the issue tracker for open bugs
- Write a test that reproduces the bug
- Fix the bug and ensure the test passes
- Submit a PR with a clear description

### Improve Documentation

- Fix typos and clarify explanations
- Add usage examples
- Improve the README
- Add architecture diagrams

## Code Style

- Python: Follow PEP 8, max line length 120
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and single-purpose
- Use meaningful variable names

## Pull Request Process

1. Ensure your code passes all tests
2. Update documentation if needed
3. Fill out the PR template completely
4. Be responsive to review feedback
5. Squash commits before merging (or we'll squash for you)

## Reporting Issues

When reporting a bug, please include:

- TransitTruth version
- Python version
- Operating system
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages or stack traces

## Feature Requests

We welcome feature requests! Please open an issue with:

- Clear description of the feature
- Why it would be useful
- Potential implementation approach (if you have one)

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

## Questions?

Feel free to open an issue or reach out to the maintainers.

Thank you for contributing! 🛡️
