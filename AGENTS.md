# AI Instructions

## Context

This is a personal app to manage finance and property mostly around french context.

## Modification Process

For each modification to the project, perform the following checks and adjustments in order:

### 1. Test Implementation (95% Coverage)

- Write unit tests to cover the modified code
- Use `uv run pytest --cov` to verify coverage
- Achieve a minimum of 95% coverage
- Use the VS Code "Code Coverage" task to generate detailed reports

### 2. Security Audit

- Check for potential vulnerabilities in modified code
- Ensure sensitive data is not exposed
- Validate that permissions and authentication are correct
- Check for SQL injections, XSS, and other common vulnerabilities
- Review dependencies for known vulnerabilities

### 3. Optimizations and Bug Fixes

- Identify unnecessary loops or N+1 queries
- Optimize database queries
- Verify error and exception handling
- Search for potential bug sources
- Ensure code follows Django best practices

### 4. French Translation Update and Completion

- Run the "Django Makemessages" task to generate translation files
- Translate all messages to French in `locale/fr/`
- Translate all user-facing strings
- Run the "Django Compilemessages" task after translations
- Verify that the interface is fully in French

### 5. Pre-commit Execution and Fixes

- Execute `uv run prek run`
- Fix all issues reported by pre-commit hooks
- This includes: code formatting, linting, quality checks
- Re-run until all hooks pass successfully
- Once fixed, run with `--all-files` to ensure no issues remain

## Recommended Execution Order

1. Develop the modification
2. Write and validate tests (95% coverage)
3. Perform security audit
4. Optimize and fix bugs
5. Update the generate_fixtures.py script if necessary
6. Update translations
7. Run pre-commit and fix issues until all checks pass

## Available Tasks

- `Django Make Migrations` - Create migrations
- `Django Migrate` - Apply migrations
- `Pytest` - Run all tests
- `Code Coverage` - Generate coverage report
- `Django Makemessages` - Generate translation files
- `Django Compilemessages` - Compile translations
- `Ruff` - Automatic formatting and linting

## Project References

- Framework: Django
- Tests: pytest with coverage
- Linting: ruff + pylint
- Package Manager: uv (UV - Python package installer)
- Format: UTF-8
- Localization: French (fr)
- Pre-commit: Enabled
