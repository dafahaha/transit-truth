## Description

Please include a summary of the changes and the related issue.

Fixes #(issue)

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] New probe (detection probe addition)
- [ ] Performance improvement
- [ ] Code refactoring

## How Has This Been Tested?

Please describe the tests that you ran to verify your changes.

- [ ] Unit tests pass (`pytest tests/ -v`)
- [ ] New tests added for new functionality
- [ ] Manual testing completed (describe below)

### Manual Testing Steps

1. 
2. 
3. 

## Checklist

- [ ] My code follows the project's code style (PEP 8, max line length 120)
- [ ] I have added type hints to all new function signatures
- [ ] I have added docstrings to new public functions and classes
- [ ] I have updated the documentation accordingly
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published in downstream modules

## Probe-Specific Checklist (if adding a probe)

- [ ] Probe has a unique ID
- [ ] Probe has expected token range (if tokenizer probe)
- [ ] Probe uses appropriate temperature (high for behavioral, low for capability)
- [ ] Randomization logic added to `randomized_probes.py`
- [ ] Tests added for the new probe
- [ ] Methodology documentation updated

## Screenshots (if applicable)

Add screenshots to help explain your changes.

## Additional Notes

Add any other context about the pull request here.
