# Documentation

Start with the [project README](../README.md) for setup and the most-used commands.

## Start here: project context and maintenance

| Guide | Read it for |
| --- | --- |
| [Project vision, brainstorming and history](PROJECT_VISION_AND_HISTORY.md) | Original goals, key trade-offs, changes over time and related repositories |
| [Current architecture, codebase and tech stack](ARCHITECTURE.md) | Module map, Python/HF/GitHub integration, data contracts and concurrency |
| [AI agent playbook](AI_AGENT_PLAYBOOK.md) | Zero-context onboarding, permission gates, development and release checklist, handover template |
| [Failures and lessons learnt](FAILURES_AND_LESSONS.md) | Past incident patterns, fixes, regressions and recovery discipline |
| [Operations and deployment](OPERATIONS_AND_DEPLOYMENT.md) | Local Windows setup, GitHub Actions, credentials, verification and deployment boundaries |
| [Roadmap](ROADMAP.md) | Delivered features, prioritised proposals, known limitations and open questions |
| [Output conventions](OUTPUT_CONVENTIONS.md) | Concise start/counts/closure and privacy-safe public Actions summaries |

**Current agent instructions:** [AGENTS.md](../AGENTS.md). The [pre-restructure
historical agent handbook](archive/AGENTS_PRE_2026-11-21.md) is retained for
background only and contains out-of-date paths/workflows.

## Everyday use

| Guide | Covers |
| --- | --- |
| [User guide and command reference](USER_GUIDE.md) | All Windows launchers, Python commands, ZIP downloads, reports, covers and limits |
| [Smart upload and deduplication](SMART_UPLOAD.md) | Matching, conflict detection, edition safety, first upload and cloud commit behaviour |
| [Library inspection](LIBRARY_INSPECTION.md) | Chapter inventory, cover audit, integrity, local Retriever comparison, evidence levels |
| [Source metadata audit and repair](METADATA_REPAIR.md) | Missing synopsis/genre/status report and safe one-novel catalogue-only JSON repair |
| [Data safety and recovery](SAFETY_AND_RECOVERY.md) | Cache cleanup, backups, full reset, confirmation and recovery limitations |
| [GitHub Actions](GITHUB_ACTIONS.md) | Run private checks, configure tokens and review automated workflows |

## Specialised topics

| Guide | Covers |
| --- | --- |
| [Source genre repair](GENRE_REPAIR.md) | Historical, opt-in missing source metadata restoration from existing artefacts |
| [Readable-folder migration history](READABLE_FOLDER_MIGRATION.md) | Completed migration procedure and safety gates, not an active migration Action |
| [Post-migration verification](POST_MIGRATION_VERIFICATION_2026-11-14.md) | Verified November 2026 migration results |
| [Cross-repository acceptance history](CROSS_REPO_READABLE_FOLDER_ACCEPTANCE.md) | Historical reader/controller validation |
| [Releasing](RELEASING.md) | CI, release notes and version tagging |

For implementation decisions and agent-maintainer instructions, see [AGENTS.md](../AGENTS.md). For release history, see [CHANGELOG.md](../CHANGELOG.md).

**Privacy:** Never commit private novel ZIPs, EPUBs, catalogue exports, ratings, personal notes, authentication tokens or local reports to this public repository.
