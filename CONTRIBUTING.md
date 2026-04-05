# Contributing to django-saladbar

## Getting Started

1. Fork the repository
2. Clone your fork
3. Make your changes
4. Run the build/check: `make check`
5. Open a pull request

## Development

No local Python installation is required. Everything runs in Docker:

```bash
make check    # Build, validate, and import-test the package
make build    # Build and copy dist artifacts locally
make clean    # Remove build artifacts
```

## Pull Requests

- Keep PRs focused on a single change
- Update the CHANGELOG if your change is user-facing
- Ensure `make check` passes

## Reporting Issues

- Use the GitHub issue templates (bug report or feature request)
- Include Django/Celery versions and steps to reproduce for bugs
