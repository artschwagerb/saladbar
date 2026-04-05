# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-04-05

### Added
- Initial release
- Dashboard with real-time worker status, task volume charts, and queue analytics
- Periodic task list with run history and schedule visualization
- Task detail view with runtime trend charts
- Task execution logs with filtering
- Result detail view with traceback display
- 24-hour schedule timeline
- Redis broker info panel
- In-flight task monitoring with long-running detection
- Error grouping by exception type
- Stale task detection
- Manual task execution, revocation, and queue purge
- Auto-refresh with countdown timer
- Permission-based access control (`can_view_saladbar`, `can_manage_saladbar`)
- Configurable base template (`SALADBAR_BASE_TEMPLATE`)
- Configurable Celery app (`SALADBAR_CELERY_APP`)
- Configurable queue names (`SALADBAR_QUEUE_NAMES`)
- Standalone base template with Bootstrap 5 and FontAwesome (works without a parent project template)
- SRI integrity hashes on all CDN resources
