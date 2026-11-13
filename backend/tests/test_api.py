from fastapi.testclient import TestClient

from app.main import create_app



def make_client() -> TestClient:
    app = create_app(
        "sqlite://",
        allowed_origins=["http://localhost:5173"],
        allowed_hosts=["testserver", "localhost", "127.0.0.1"],
    )
    return TestClient(app)


def test_health_checks_database_and_seeds_unconfigured_manager() -> None:
    with make_client() as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["database"] == "ok"

        agents = client.get("/api/v1/agents").json()
        assert len(agents) == 1
        assert agents[0]["id"] == "manager"
        assert agents[0]["provider"] == "unconfigured"
        assert agents[0]["is_manager"] is True


def test_project_agent_task_creation_and_dashboard_counts() -> None:
    with make_client() as client:
        project_response = client.post(
            "/api/v1/projects",
            json={"name": "Example", "description": "API integration test"},
        )
        assert project_response.status_code == 201
        project = project_response.json()

        agent_response = client.post(
            "/api/v1/agents",
            json={"name": "Worker One", "role": "QA Engineer"},
        )
        assert agent_response.status_code == 201
        agent = agent_response.json()

        task_response = client.post(
            "/api/v1/tasks",
            json={
                "project_id": project["id"],
                "title": "Verify initial API",
                "assigned_agent_id": agent["id"],
                "acceptance_criteria": ["API returns persisted records"],
            },
        )
        assert task_response.status_code == 201
        task = task_response.json()
        assert task["state"] == "assigned"
        assert task["assigned_agent_id"] == agent["id"]

        dashboard = client.get("/api/v1/dashboard").json()
        assert dashboard["projects"]["total"] == 1
        assert dashboard["agents"]["total"] == 2
        assert dashboard["agents"]["workers"] == 1
        assert dashboard["tasks"]["total"] == 1
        assert dashboard["tasks"]["by_state"] == {"assigned": 1}
        assert len(dashboard["recent_events"]) >= 4


def test_task_rejects_missing_project_and_assignment_can_be_cleared() -> None:
    with make_client() as client:
        missing_project = client.post(
            "/api/v1/tasks",
            json={"project_id": "missing", "title": "Must not be created"},
        )
        assert missing_project.status_code == 404
        missing_dependency = client.post(
            "/api/v1/tasks",
            json={"title": "Invalid dependency", "dependencies": ["missing"]},
        )
        assert missing_dependency.status_code == 404
        duplicate_dependencies = client.post(
            "/api/v1/tasks",
            json={"title": "Duplicate dependencies", "dependencies": ["same", "same"]},
        )
        assert duplicate_dependencies.status_code == 422

        agent = client.post(
            "/api/v1/agents",
            json={"name": "Worker", "role": "Backend Developer"},
        ).json()
        task = client.post(
            "/api/v1/tasks",
            json={"title": "Unassignable until set", "assigned_agent_id": agent["id"]},
        ).json()

        response = client.patch(
            f"/api/v1/tasks/{task['id']}/assignment",
            json={"assigned_agent_id": None},
        )
        assert response.status_code == 200
        assert response.json()["assigned_agent_id"] is None
        assert response.json()["state"] == "pending"


def test_role_catalog_has_twenty_distinct_worker_templates() -> None:
    with make_client() as client:
        roles = client.get("/api/v1/agent-roles").json()
        assert len(roles) == 20
        assert len({role["id"] for role in roles}) == 20


def test_worker_limit_is_enforced() -> None:
    with make_client() as client:
        for index in range(20):
            response = client.post(
                "/api/v1/agents",
                json={"name": f"Worker {index}", "role": "General Development Agent"},
            )
            assert response.status_code == 201

        response = client.post(
            "/api/v1/agents",
            json={"name": "Too many", "role": "General Development Agent"},
        )
        assert response.status_code == 409


def test_file_database_survives_application_restart_and_migrations_are_idempotent(tmp_path) -> None:
    database_path = tmp_path / "aatm.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"

    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as first_client:
        created = first_client.post("/api/v1/projects", json={"name": "Persistent project"})
        assert created.status_code == 201
        project_id = created.json()["id"]

    with TestClient(create_app(database_url, allowed_hosts=["testserver"])) as second_client:
        projects = second_client.get("/api/v1/projects").json()
        assert [project["id"] for project in projects] == [project_id]
        assert second_client.get("/api/v1/health").status_code == 200


def test_untrusted_host_is_rejected() -> None:
    with make_client() as client:
        response = client.get("/api/v1/health", headers={"host": "attacker.invalid"})
        assert response.status_code == 400
