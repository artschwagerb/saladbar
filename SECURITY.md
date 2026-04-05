# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email **security@bartschwager.com** with a description of the vulnerability
3. Include steps to reproduce if possible

You should receive a response within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

Saladbar is a monitoring dashboard. By design, it exposes Celery task metadata (task names, arguments, results, tracebacks, worker info, and Redis broker stats) to authenticated users with the `can_view_saladbar` permission. Users with `can_manage_saladbar` can execute, revoke, and purge tasks.

**Grant these permissions carefully** — they provide broad visibility into your task infrastructure.
