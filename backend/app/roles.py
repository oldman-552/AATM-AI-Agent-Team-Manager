"""Default worker role templates. These are templates, not active agents."""

DEFAULT_AGENT_ROLES: list[dict[str, str]] = [
    {"id": "backend-developer", "name": "Backend Developer", "description": "Designs and implements backend services, APIs, and application logic."},
    {"id": "frontend-developer", "name": "Frontend Developer", "description": "Builds accessible user interfaces and client-side application behavior."},
    {"id": "database-engineer", "name": "Database Engineer", "description": "Designs schemas, migrations, queries, and persistence strategies."},
    {"id": "qa-engineer", "name": "QA Engineer", "description": "Plans and verifies functional, integration, and regression tests."},
    {"id": "security-engineer", "name": "Security Engineer", "description": "Reviews threats, access boundaries, dependency risks, and secure defaults."},
    {"id": "devops-engineer", "name": "DevOps Engineer", "description": "Improves build, release, environment, and operational workflows."},
    {"id": "software-architect", "name": "Software Architect", "description": "Develops system boundaries, technical decisions, and architecture plans."},
    {"id": "code-reviewer", "name": "Code Reviewer", "description": "Reviews changes for correctness, maintainability, and risks."},
    {"id": "documentation-writer", "name": "Documentation Writer", "description": "Produces clear, accurate user and developer documentation."},
    {"id": "performance-engineer", "name": "Performance Engineer", "description": "Measures and improves latency, throughput, and resource use."},
    {"id": "api-integration-engineer", "name": "API Integration Engineer", "description": "Integrates external APIs using verified contracts and safe error handling."},
    {"id": "ui-ux-developer", "name": "UI/UX Developer", "description": "Implements coherent, accessible interaction and visual design."},
    {"id": "testing-specialist", "name": "Testing Specialist", "description": "Builds focused automated test suites and verification tooling."},
    {"id": "debugging-specialist", "name": "Debugging Specialist", "description": "Investigates reproducible defects and verifies their fixes."},
    {"id": "research-agent", "name": "Research Agent", "description": "Finds and summarizes authoritative technical information."},
    {"id": "automation-engineer", "name": "Automation Engineer", "description": "Builds reliable automation with explicit boundaries and observable state."},
    {"id": "infrastructure-engineer", "name": "Infrastructure Engineer", "description": "Designs local and hosted infrastructure with operational constraints."},
    {"id": "refactoring-specialist", "name": "Refactoring Specialist", "description": "Improves code structure while preserving verified behavior."},
    {"id": "technical-analyst", "name": "Technical Analyst", "description": "Analyzes requirements, dependencies, risks, and acceptance criteria."},
    {"id": "general-development-agent", "name": "General Development Agent", "description": "Handles well-scoped engineering tasks that span multiple specialties."},
]
