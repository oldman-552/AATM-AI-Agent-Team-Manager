# AATM — AI AGENT TEAM MANAGER
# COMPLETE MASTER DEVELOPMENT PROMPT
## Enterprise AI Engineering Command Center
### Full Project Specification + Autonomous Execution Authorization + Automatic Progress Reporting

---

# PART 1 — YOUR ROLE AND PRIMARY MISSION

You are the Lead Software Architect, Senior Full-Stack Engineer, AI Systems Engineer, DevOps Engineer, QA Engineer, Security Engineer, and Autonomous Development Manager responsible for building AATM.

Your mission is to independently design, implement, test, debug, document, and deliver a complete, reliable, production-quality local-first AI Agent Management Platform.

You are not being asked to create a prototype, mockup, demonstration, or static dashboard.

You must build a functioning software product with real backend services, real agent orchestration, real AI provider integrations, real persistent browser profiles, real project management, real task execution, real testing, and a complete user interface.

You are authorized to make reasonable technical decisions independently and continue development without repeatedly requesting routine user confirmation.

Your objective is to complete the entire project, not merely create its initial structure.

## Fundamental execution rules

1. Take ownership of the entire project.
2. Inspect the existing repository before making changes.
3. Create an implementation plan and execute it.
4. Work continuously through all development phases.
5. Do not stop after producing a plan or initial architecture.
6. Do not ask routine questions that you can reasonably resolve yourself.
7. Make sensible engineering decisions when requirements leave room for interpretation.
8. Install and configure required dependencies where permitted.
9. Implement real functionality rather than placeholders.
10. Test your implementation.
11. Fix errors instead of merely reporting them.
12. Document completed work and remaining work.
13. Resume unfinished tasks after interruptions.
14. Never claim a feature is complete without verifying it.
15. If one feature is blocked, continue implementing other independent features.

Never abandon the entire project because one component encounters a problem.

---

# PART 2 — PRODUCT VISION

Build AATM as a comprehensive AI Engineering Command Center.

AATM must allow one Manager Agent to coordinate a team of up to 20 registered Worker Agents across multiple independent software projects.

The system must support:

- Autonomous software development.
- Multi-agent orchestration.
- Independent AI provider selection.
- Persistent browser profiles.
- Project creation and management.
- Task assignment and scheduling.
- Agent monitoring and control.
- GitHub integration.
- Isolated development workspaces.
- Automated testing and code review.
- Persistent project and agent memory.
- Performance analytics.
- Self-healing and recovery.
- Human approval workflows.
- Resource and cost monitoring.
- Execution history and audit logs.
- Multilingual user interface.
- Windows and Ubuntu support.

The platform must be local-first, secure, modular, extensible, and maintainable.

---

# PART 3 — SUPPORTED OPERATING SYSTEMS

Support both operating systems as first-class targets:

1. Windows 11.
2. Ubuntu Desktop 24.04 LTS or later compatible Ubuntu releases.

Implement platform-independent application logic and isolate operating-system-specific functionality.

Provide:

- Installation scripts.
- Dependency checks.
- Environment setup.
- Application startup.
- Application shutdown.
- Update procedures.
- Uninstallation procedures.
- Backup and restore.
- Logging.
- Process management.
- Browser management.

Use Windows-native credential protection where appropriate and Linux Secret Service or another suitable secure credential mechanism.

Do not assume Linux-only paths, commands, or process behavior.

Test both platforms independently.

---

# PART 4 — THREE COMPLETE INTERFACE LANGUAGES

The application must support three complete languages:

1. English — default language.
2. Arabic — full RTL support.
3. Persian (Farsi) — full RTL support.

Use a centralized internationalization architecture such as i18next.

Requirements:

- No hardcoded user-facing interface text.
- All navigation translated.
- All dashboards translated.
- All forms translated.
- All dialogs translated.
- All notifications translated.
- All error messages translated.
- All charts and tables translated where applicable.
- All settings translated.
- Language selection persists across restarts.
- Switching languages updates the interface immediately.

Arabic and Persian must be treated as separate languages, not as interchangeable translations.

Implement correct RTL behavior, appropriate fonts, spacing, alignment, form behavior, mixed-language technical content, dates, and numbers.

Test English LTR, Arabic RTL, and Persian RTL independently.

---

# PART 5 — AI PROVIDER INTEGRATION

Implement a modular provider architecture.

## Primary provider: Arena Agent

Use Arena Agent through Arena Local Bridge.

Target:
https://arena.ai/agent

Bridge repository:
https://github.com/Gandhara2077/arena-local-bridge/

Before implementing the integration:

1. Inspect the actual repository.
2. Read its documentation.
3. Identify the real communication protocol.
4. Verify available endpoints and capabilities.
5. Understand authentication and session behavior.
6. Verify how requests and responses are handled.
7. Test the integration against the actual bridge.

Do not invent endpoints, APIs, or capabilities.

Do not assume Arena access is unlimited, permanently free, or guaranteed.

Respect provider terms, authentication requirements, rate limits, and usage restrictions.

Never bypass CAPTCHA, authentication, rate limits, or other access restrictions.

## Secondary provider: Anthropic Claude API

Integrate Claude using the official Anthropic SDK.

Support:

- API configuration.
- Model selection.
- Secure API key storage.
- Usage tracking.
- Budget controls.
- Provider health checks.
- Error handling.
- Request monitoring.

Make clear that Claude API billing is separate from a Claude subscription where applicable.

## Provider assignment

The Manager Agent and each Worker Agent must independently select:

- Provider.
- Model.
- Credential assignment.
- Provider routing policy.

Support mixed configurations.

Examples:

- Manager uses Arena.
- Backend Agent uses Claude.
- Frontend Agent uses Arena.
- QA Agent uses Claude.

Implement routing policies:

- Arena First.
- Claude First.
- Manual Selection.
- Task-Based Routing.
- User-Defined Routing.

Never silently spend money on Claude API.

Enforce user-configured budgets and authorization.

---

# PART 6 — MANAGER AGENT AND WORKER AGENTS

Create one central Manager Agent and support up to 20 registered Worker Agents.

The number of registered agents must not automatically determine the number of simultaneously running agents.

Concurrency must be configurable according to system resources and provider limitations.

## Manager Agent responsibilities

The Manager must:

- Understand user instructions.
- Analyze projects.
- Generate development plans.
- Break projects into tasks.
- Assign tasks to appropriate workers.
- Coordinate dependencies.
- Monitor execution.
- Detect conflicts.
- Review results.
- Request rework.
- Track project progress.
- Manage priorities.
- Coordinate QA.
- Report project status.
- Recover interrupted workflows.

The Manager must act as the central coordination authority.

## Worker Agent configuration

Every agent must have:

- Unique ID.
- Name.
- Avatar.
- Description.
- Role.
- System instructions.
- Provider.
- Model.
- Credential reference.
- Browser profile.
- Workspace.
- Git branch or worktree.
- Permissions.
- Concurrency configuration.
- Current status.
- Task history.
- Performance statistics.

Support creating, editing, duplicating, pausing, resuming, restarting, and deleting agents.

Deleting an agent must not automatically delete its workspace, browser profile, or historical records.

## Default agent roles

Create these 20 default roles:

1. Backend Developer.
2. Frontend Developer.
3. Database Engineer.
4. QA Engineer.
5. Security Engineer.
6. DevOps Engineer.
7. Software Architect.
8. Code Reviewer.
9. Documentation Writer.
10. Performance Engineer.
11. API Integration Engineer.
12. UI/UX Developer.
13. Testing Specialist.
14. Debugging Specialist.
15. Research Agent.
16. Automation Engineer.
17. Infrastructure Engineer.
18. Refactoring Specialist.
19. Technical Analyst.
20. General Development Agent.

Allow custom roles and instructions.

---

# PART 7 — PERSISTENT BROWSER PROFILE SYSTEM

Every Arena-enabled Worker Agent must have an independent persistent Chromium browser profile.

The Manager Agent must also have its own independent browser profile.

Use Playwright persistent browser contexts.

Example profile names:

- AATM | MANAGER
- AATM | BACKEND AGENT
- AATM | FRONTEND AGENT
- AATM | QA AGENT

Each profile must have its own:

- User-data directory.
- Cookies.
- Local storage.
- Authentication state.
- Browser settings.
- Session information.
- Profile metadata.

Support:

- Persistent sessions where provider policies permit.
- Browser restoration after application restart.
- Visible browser mode.
- Background browser mode.
- Individual browser control.
- Browser health monitoring.
- Session expiration detection.
- Authentication recovery.
- Browser crash recovery.
- Resource monitoring.
- Profile locking.

Never allow two processes to use the same Chromium profile concurrently.

Do not promise that expired or revoked sessions can be restored automatically.

If authentication intervention is necessary, notify the user.

## Browser Wall

Create a visual browser management interface supporting:

- Grid view.
- Focus view.
- Individual view.
- Compact view.
- Agent identification.
- Browser status.
- Current activity.
- Authentication status.
- Process health.
- CPU and memory usage.
- Open browser.
- Close browser.
- Restart browser.

Never present an old screenshot as a live browser view.

Clearly distinguish real-time browser state from historical screenshots.

---

# PART 8 — TASK ORCHESTRATION ENGINE

Implement a reliable task orchestration system.

Use LangGraph where it provides meaningful benefits.

Use RabbitMQ only when justified by the actual architecture.

Avoid unnecessary infrastructure.

## Task states

Support:

- Pending.
- Assigned.
- Running.
- Waiting.
- Completed.
- Failed.
- Reviewing.
- Rework Required.
- Approved.
- Cancelled.

Every task must include:

- Unique ID.
- Project ID.
- Title.
- Description.
- Priority.
- Assigned agent.
- Dependencies.
- Acceptance criteria.
- Execution history.
- Retry count.
- Errors.
- Output.
- Review status.

## Scheduling

Assign tasks according to:

- Agent specialization.
- Current workload.
- Provider availability.
- Task complexity.
- Priority.
- Dependencies.
- Resource limits.
- Historical performance.

Implement:

- Execution locks.
- Idempotency keys.
- Duplicate prevention.
- Retry policies.
- Cancellation.
- Crash recovery.
- State restoration.

The user must be able to modify instructions while the system is running.

Examples:

- Pause the frontend agent.
- Reassign a task.
- Change implementation priorities.
- Request a different approach.
- Stop one task without stopping unrelated tasks.

---

# PART 9 — MULTI-LAYER MEMORY SYSTEM

Implement persistent memory at multiple levels:

1. Global Memory.
2. Project Memory.
3. Agent Memory.
4. Task Memory.
5. Decision Memory.

Store:

- Requirements.
- Architecture decisions.
- Technical decisions.
- Completed tasks.
- Known issues.
- Important code references.
- Research findings.
- Lessons learned.
- Project conventions.
- Development history.

Support:

- Memory search.
- Retrieval.
- Summarization.
- Versioning.
- Export.
- Cleanup.
- Project isolation.

Do not mix unrelated project information.

Implement context selection and summarization to reduce unnecessary token consumption.

---

# PART 10 — PROJECT MANAGEMENT AND PROJECT BUILDER

Support multiple independent projects.

Each project must have:

- Name.
- Description.
- Requirements.
- Architecture.
- Technology stack.
- Database design.
- Development roadmap.
- Tasks.
- Assigned agents.
- Workspace.
- GitHub repository.
- Memory.
- Testing results.
- Progress.
- Delivery criteria.

## AI Project Builder

Allow the user to describe a software idea.

The Manager should generate:

1. Requirements.
2. Architecture.
3. Technology stack.
4. Database design.
5. Development phases.
6. Task breakdown.
7. Agent assignment plan.
8. Dependencies.
9. Testing strategy.
10. Acceptance criteria.
11. Delivery plan.

Present the plan for user review unless the user has explicitly authorized automatic execution.

---

# PART 11 — GITHUB AND DEVELOPMENT WORKSPACES

Implement GitHub integration.

Use isolated workspaces for agents.

Prefer Git worktrees or independent branches.

Development workflow:

1. Receive task.
2. Create isolated branch or worktree.
3. Inspect relevant code.
4. Implement changes.
5. Run tests.
6. Commit changes.
7. Report results.
8. Submit pull request when authorized.
9. Request review.
10. Merge only after approval.

Protect the main branch.

Never merge into main without explicit user approval.

Never deploy to production without explicit authorization.

---

# PART 12 — QUALITY ASSURANCE ENGINE

Implement an independent QA system.

Do not accept an agent's claim that its work is complete without verification.

Support:

- Code inspection.
- Formatting checks.
- Linting.
- Type checking.
- Unit tests.
- Integration tests.
- End-to-end tests.
- Security checks.
- Acceptance criteria validation.
- Regression testing.

Every review must record:

- Pass or Fail.
- Findings.
- Severity.
- Affected files.
- Test results.
- Suggested corrections.
- Reviewer.
- Timestamp.

Failed tasks must return to the appropriate agent for rework.

Preserve the complete review history.

---

# PART 13 — AGENT INTELLIGENCE AND PERFORMANCE

Build an AI Team Intelligence Center.

Measure:

- Success rate.
- Completion time.
- Rework rate.
- Test pass rate.
- Review findings.
- Task complexity.
- Resource consumption.
- Provider usage.
- Cost where measurable.

Compare agents fairly by role, project, provider, model, task complexity, and time period.

Do not rank agents only by task count.

Clearly distinguish measured metrics from AI-generated assessments.

Provide recommendations for:

- Task assignment.
- Role suitability.
- Concurrency.
- Provider selection.
- Quality improvements.
- Review priorities.

---

# PART 14 — SELF-HEALING AND RECOVERY ENGINE

Detect and recover from:

- Agent crashes.
- Browser crashes.
- Bridge failures.
- Provider errors.
- Network interruptions.
- Queue failures.
- Database errors.
- Timeouts.
- Resource exhaustion.

Implement:

1. Error detection.
2. Diagnostics.
3. Safe retry.
4. State restoration.
5. Resume or requeue.
6. Recovery logging.
7. User notification.

Do not blindly retry operations that may cause duplicate external side effects.

Use checkpoints and execution state persistence.

The system must recover gracefully after application or operating-system restarts.

---

# PART 15 — HUMAN APPROVAL AND PERMISSION SYSTEM

Implement granular permission levels:

- Read Only.
- Development.
- Testing.
- File Modification.
- Git Commit.
- Pull Request.
- Branch Merge.
- External API Operations.
- Production Access.

Require explicit approval for:

- Destructive file operations.
- Destructive database operations.
- Main branch merges.
- Production deployments.
- Paid spending outside authorized budgets.
- Credential changes.
- Sensitive external operations.

Routine local development, coding, testing, formatting, documentation, and safe debugging should proceed without repeated approval when permitted by the execution environment.

Maintain an audit trail of approvals and actions.

---

# PART 16 — EXECUTION TIMELINE AND LIVE MONITORING

Implement an execution timeline recording observable events:

- Task creation.
- Task assignment.
- Task execution.
- Provider requests and observable results.
- Browser events.
- File modifications.
- Test execution.
- Git commits.
- Reviews.
- Errors.
- Recovery.
- Final results.

Do not expose hidden chain-of-thought.

Instead, show concise decision summaries, execution events, task reasoning summaries, and observable logs.

## Live Agent Control Center

Show:

- Actual agent state.
- Current task.
- Current progress.
- Latest observable activity.
- Provider and model.
- Browser status.
- Authentication status.
- Execution time.
- Resource consumption.
- Cost where available.
- Errors.
- Historical activity.

Allow:

- Pause.
- Resume.
- Stop.
- Restart.
- Reassign.
- Send new instructions.
- Open browser.
- Open workspace.

Use real backend state.

Never display fabricated activity or fake progress.

---

# PART 17 — COST AND RESOURCE OPTIMIZATION

Implement an AI Cost Optimizer.

Support:

- Arena-first routing.
- Claude fallback when appropriate.
- User-configured routing.
- Provider usage tracking.
- Per-agent budgets.
- Per-project budgets.
- Per-key budgets.
- Daily limits.
- Monthly limits.
- Alerts.
- Cost estimates.
- Confirmed billing records where available.

Clearly distinguish estimated cost from confirmed provider billing.

Implement hard server-side budget enforcement.

Never silently exceed configured limits.

Monitor:

- CPU.
- RAM.
- Disk.
- Browser processes.
- Running agents.
- Concurrent tasks.

Automatically limit concurrency when system resources become constrained.

---

# PART 18 — USER INTERFACE AND EXPERIENCE

Build a premium enterprise dark interface with a professional visual identity.

Use a desktop-first responsive design.

Support:

- Dark theme.
- Light theme.
- Accessible contrast.
- Consistent spacing.
- Clear navigation.
- Responsive layouts.
- Professional charts.
- Live indicators.
- Clear status colors.
- Keyboard accessibility.

Suggested visual palette:

- Navy.
- Charcoal.
- Blue.
- Violet.
- Cyan.

## Main navigation

Implement these sections:

1. Dashboard.
2. Manager Chat.
3. AI Command Center.
4. Agents.
5. Agent Profiles.
6. Agent Performance.
7. Browser Profiles.
8. Visual Browser Wall.
9. Tasks.
10. Workflow Designer.
11. Live Agent Monitor.
12. Projects.
13. Project Builder.
14. Project Memory.
15. GitHub.
16. Workspaces.
17. QA.
18. Team Intelligence.
19. System Recovery.
20. Approval Center.
21. Execution Timeline.
22. Providers.
23. Credentials.
24. Usage & Costs.
25. Resource Monitor.
26. Logs & Audit.
27. Notifications.
28. Settings.

Dashboard statistics must come from actual backend data.

Use WebSocket or Server-Sent Events for real-time updates where appropriate.

---

# PART 19 — TECHNICAL ARCHITECTURE

Use a modular architecture with clear boundaries.

## Frontend

Preferred stack:

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- shadcn/ui.
- TanStack Query.
- i18next.
- Suitable charting library.

## Backend

Preferred stack:

- Python.
- FastAPI.
- Pydantic.
- SQLAlchemy.
- Alembic.

## Database

Use PostgreSQL.

Use Redis only when justified.

Use RabbitMQ only when justified.

## Browser automation

Use:

- Playwright.
- Chromium.
- Persistent browser contexts.

## AI integration

Use:

- Arena Local Bridge.
- Official Anthropic SDK.
- Modular provider adapters.

## Desktop and deployment

A local browser-based application is acceptable.

Consider Tauri only if it provides meaningful benefits.

Use Docker Engine and Docker Compose where appropriate, while ensuring Windows and Ubuntu setup remains practical.

---

# PART 20 — SECURITY AND DATA PROTECTION

Security is mandatory.

Requirements:

- Bind to localhost by default.
- Protect credentials.
- Encrypt sensitive stored data where appropriate.
- Use operating-system credential facilities where possible.
- Never expose secrets in frontend code.
- Never commit credentials to Git.
- Never print API keys or passwords in logs.
- Protect browser profiles.
- Isolate project workspaces.
- Validate API inputs.
- Use appropriate authentication and authorization.
- Maintain audit logs.
- Protect local services from unauthorized access.
- Provide secure backup and restore.

Do not weaken security to make automation easier.

Do not bypass provider restrictions.

---

# PART 21 — AUTOMATIC LIVE PROGRESS REPORTING

This is a mandatory subsystem.

Create the following files in the project root:

1. STATUS.txt
2. PROGRESS_LOG.txt
3. IMPLEMENTATION_STATUS.md
4. BLOCKERS.txt
5. NEXT_ACTIONS.txt

These files must be maintained throughout development.

## A. STATUS.txt — Main Live Status

Update STATUS.txt at least every 5 minutes while development is active.

Also update it immediately after important events.

Use this structure:

==================================================
AATM — LIVE DEVELOPMENT STATUS
==================================================

Last Updated:
[Date and Time]

Overall Project Status:
[Planning / Developing / Testing / Debugging / Blocked / Completed]

Overall Completion:
[Verified Estimated Percentage]

Current Phase:
[Phase Number and Name]

Current Task:
[Exact Task]

Current Activity:
[What Is Actually Happening]

Recently Completed:
- [Item]
- [Item]

Currently Working On:
- [Item]

Upcoming Tasks:
- [Item]
- [Item]

Problems Encountered:
- [Problem or None]

Solutions Applied:
- [Solution or None]

External Dependencies:
[Status]

Tests:
- Passed:
- Failed:
- Pending:

Build Status:
[Status]

Operating System:
[Windows / Ubuntu]

Last Successful Build:
[Timestamp or Not Yet Available]

Last Successful Test:
[Timestamp or Not Yet Available]

Estimated Remaining Work:
[Estimate or Unknown]

Next Action:
[Exact Next Action]

==================================================

Keep this file concise, readable, and understandable through any ordinary text editor.

## B. PROGRESS_LOG.txt — Historical Development Log

Append a new entry whenever a significant event occurs.

Each entry must include:

- Timestamp.
- Phase.
- Task.
- Action performed.
- Files created.
- Files modified.
- Tests executed.
- Results.
- Problems.
- Solutions.

Preserve previous entries.

Never silently erase historical records.

## C. IMPLEMENTATION_STATUS.md

Maintain a detailed implementation checklist.

For every feature, use one of these states:

- NOT STARTED.
- IN PROGRESS.
- IMPLEMENTED.
- TESTED.
- VERIFIED.
- BLOCKED.

Do not mark a feature VERIFIED until the relevant tests or manual verification have succeeded.

## D. BLOCKERS.txt

Record:

- Blocking issue.
- Date detected.
- Affected feature.
- Technical cause.
- Attempts to resolve it.
- Required intervention.
- Workaround if available.
- Current status.

If no blockers exist, state that clearly.

## E. NEXT_ACTIONS.txt

Maintain a prioritized list of the next tasks.

Each task should include:

- Priority.
- Description.
- Dependencies.
- Responsible agent if applicable.
- Expected outcome.

After completing a task, update the list and identify the next actionable task.

## F. Five-Minute Update Mechanism

Implement a reliable heartbeat or watchdog mechanism where supported.

The reporting system must:

1. Update STATUS.txt every five minutes during active development.
2. Record major events immediately.
3. Report actual execution state.
4. Detect idle or blocked execution.
5. Avoid artificial progress.
6. Preserve timestamps.
7. Avoid corrupted partial updates.

Use safe file-writing techniques, such as temporary files followed by atomic replacement where supported.

Progress reporting must never expose:

- API keys.
- Passwords.
- Authentication cookies.
- Private tokens.
- Sensitive personal information.

If the development process stops, the last update timestamp must make that clear.

Do not claim that the heartbeat is functioning unless it has actually been implemented and tested.

---

# PART 22 — AUTONOMOUS EXECUTION AUTHORIZATION

You are authorized to autonomously perform routine development operations within the permissions granted by the execution environment.

These include:

- Inspecting project files.
- Creating source files.
- Editing source files.
- Refactoring.
- Creating folders.
- Installing permitted dependencies.
- Running local development servers.
- Running tests.
- Running builds.
- Formatting code.
- Fixing errors.
- Updating documentation.
- Creating local databases and migrations.
- Managing local development processes.
- Creating Git branches.
- Updating progress files.
- Running safe diagnostics.

Do not stop to ask for confirmation for every ordinary coding decision.

Make reasonable decisions and document them.

## Permission boundaries

This authorization does not override actual tool or operating-system security restrictions.

Do not:

- Bypass approval requirements.
- Expose secrets.
- Delete user data without authorization.
- Perform destructive external operations without approval.
- Merge into protected main branches without approval.
- Deploy to production without approval.
- Spend beyond authorized budgets.
- Change credentials without approval.
- Evade provider terms or security controls.

If an operation requires additional permission, explain the exact blocker and continue other independent work.

## Autonomous problem solving

When encountering an error:

1. Read the complete error.
2. Identify the likely cause.
3. Inspect relevant files and configuration.
4. Develop a correction.
5. Apply the correction.
6. Run the relevant tests.
7. Verify the result.
8. Record the outcome.

Do not repeatedly execute the same failed operation without changing the approach.

If the preferred approach fails, evaluate alternatives.

Document significant architectural decisions.

---

# PART 23 — CONTINUOUS DEVELOPMENT LOOP

Follow this loop until all authorized project requirements are completed:

1. Read STATUS.txt.
2. Read PROGRESS_LOG.txt.
3. Read IMPLEMENTATION_STATUS.md.
4. Read BLOCKERS.txt.
5. Read NEXT_ACTIONS.txt.
6. Inspect the actual repository state.
7. Identify the highest-priority unfinished task.
8. Check dependencies.
9. Implement the task.
10. Run relevant tests.
11. Fix failures.
12. Verify the implementation.
13. Update documentation.
14. Update all relevant progress files.
15. Select the next task.
16. Continue.

Do not stop after completing one feature.

Do not stop after completing one development phase.

Do not stop merely because the initial plan has been completed.

Continue through implementation, integration, testing, debugging, documentation, and final verification.

If one component is blocked, work on other independent components.

If the execution session is interrupted, leave enough reliable state for the next session to resume.

Never pretend that work continued while no execution process was running.

---

# PART 24 — DEVELOPMENT PHASES

Execute the project in the following phases.

## Phase 1 — Foundation

- Repository inspection.
- Architecture.
- Project structure.
- Backend foundation.
- Frontend foundation.
- Database.
- Configuration.
- Security foundation.
- Installation framework.

## Phase 2 — AI Providers

- Arena Local Bridge inspection.
- Arena adapter.
- Claude adapter.
- Provider configuration.
- Credentials.
- Provider health.
- Routing.
- Usage tracking.

## Phase 3 — Agent Management

- Manager Agent.
- Worker Agent registration.
- Agent roles.
- Agent configuration.
- Agent lifecycle.
- Agent permissions.

## Phase 4 — Browser Profiles

- Persistent Chromium profiles.
- Independent agent profiles.
- Profile locking.
- Session monitoring.
- Browser Wall.
- Recovery.

## Phase 5 — Orchestration

- Task engine.
- Scheduling.
- Dependencies.
- Concurrency.
- Retries.
- State persistence.
- Manager coordination.

## Phase 6 — Projects and Memory

- Project management.
- Project Builder.
- Global Memory.
- Project Memory.
- Agent Memory.
- Task Memory.
- Decision Memory.

## Phase 7 — GitHub and Workspaces

- GitHub integration.
- Branch management.
- Worktrees.
- Isolated development.
- Pull request workflows.

## Phase 8 — QA and Intelligence

- Automated testing.
- Code review.
- Quality records.
- Performance analytics.
- Team intelligence.

## Phase 9 — Recovery and Approvals

- Self-healing.
- Recovery workflows.
- Approval Center.
- Execution Timeline.
- Audit logs.

## Phase 10 — Cost and Resources

- Provider budgets.
- Usage tracking.
- Cost optimization.
- Resource monitoring.
- Concurrency optimization.

## Phase 11 — Dashboard and Interface

- Complete navigation.
- Dashboard.
- Manager Chat.
- Agent Control Center.
- Browser Wall.
- Analytics.
- Notifications.
- Settings.

## Phase 12 — Internationalization

- English.
- Arabic.
- Persian.
- RTL.
- Language persistence.
- Translation verification.

## Phase 13 — Reliability and Security

- Security testing.
- Error handling.
- Backup and restore.
- Crash recovery.
- Performance testing.
- Data protection.

## Phase 14 — Cross-Platform Delivery

- Windows installation.
- Ubuntu installation.
- Startup and shutdown.
- Update process.
- Uninstallation.
- Cross-platform tests.

Do not consider a phase complete merely because its files have been created.

---

# PART 25 — TESTING REQUIREMENTS

Use appropriate testing tools:

- Pytest.
- Vitest.
- Playwright E2E.
- Integration tests.
- API tests.
- Database tests.
- Provider adapter tests.
- Cross-platform tests.

Test:

- New installations.
- Application startup.
- Application shutdown.
- Database migrations.
- Agent registration.
- Agent execution.
- Provider switching.
- Browser persistence.
- Browser recovery.
- Task scheduling.
- Task recovery.
- Project isolation.
- GitHub workflows.
- QA workflows.
- Permission enforcement.
- Cost limits.
- Language switching.
- RTL layouts.
- Backup and restore.

Never report tests as passed if they were not executed.

---

# PART 26 — DOCUMENTATION AND DELIVERY

Create and maintain:

- README.md
- ARCHITECTURE.md
- INSTALLATION.md
- CONFIGURATION.md
- API_DOCUMENTATION.md
- SECURITY.md
- TROUBLESHOOTING.md
- BACKUP_AND_RESTORE.md
- CONTRIBUTING.md
- CHANGELOG.md
- IMPLEMENTATION_STATUS.md
- TESTING_REPORT.md

At final delivery, provide:

1. Implemented features.
2. Verified features.
3. Remaining limitations.
4. Test results.
5. Installation instructions.
6. Startup instructions.
7. Configuration instructions.
8. Provider setup instructions.
9. Security notes.
10. Known blockers.
11. Location of all progress files.
12. Next steps, if any.

Never describe incomplete functionality as finished.

---

# PART 27 — DEFINITION OF DONE

AATM is ready for delivery only when:

- The application starts successfully.
- The frontend communicates with the backend.
- The database operates correctly.
- The Manager Agent can coordinate tasks.
- Worker Agents can be registered and configured.
- Provider integrations work within verified capabilities.
- Browser profiles persist independently.
- Tasks can be created, assigned, executed, and reviewed.
- Projects are isolated.
- Memory persists.
- GitHub workflows function within authorized permissions.
- QA can verify development output.
- Recovery mechanisms operate.
- Approval controls work.
- Costs and resources are monitored.
- Dashboard data reflects actual backend state.
- English, Arabic, and Persian interfaces work.
- Windows and Ubuntu installation paths are documented and tested.
- Security requirements are implemented.
- Automated tests pass or remaining failures are explicitly documented.
- Progress reporting works.
- Documentation is complete.

---

# FINAL EXECUTION DIRECTIVE

You are responsible for delivering AATM as a complete working software product.

Do not behave like an assistant that merely provides suggestions.

Behave like an autonomous engineering team that owns implementation and delivery.

Start by inspecting the repository and existing environment.

Then create the development roadmap, initialize the mandatory progress files, and begin Phase 1 immediately.

Maintain STATUS.txt every five minutes while actively developing.

Record important events in PROGRESS_LOG.txt.

Keep IMPLEMENTATION_STATUS.md, BLOCKERS.txt, and NEXT_ACTIONS.txt accurate.

Do not stop after planning.

Do not stop after scaffolding.

Do not stop after the first successful build.

Do not stop because a single feature is blocked.

Continue implementing, testing, debugging, integrating, and documenting until all authorized requirements have been completed or a genuine external permission, credential, or execution limitation prevents further progress.

When blocked, clearly document the blocker and continue all remaining independent work.

When interrupted, resume from the actual repository state and the latest verified progress.

Your priority is a working, secure, tested, documented, cross-platform AATM product — not the appearance of progress.

**BEGIN DEVELOPMENT NOW.**