from pathlib import Path

import yaml


def test_docker_compose_uses_component_services_and_external_env_file():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    assert set(compose["services"]) >= {"app", "nginx"}
    assert compose["services"]["app"]["env_file"] == ["/opt/rag-challenge/.env"]
    assert compose["services"]["app"]["volumes"] == ["rag_data:/app/data"]
    assert compose["services"]["nginx"]["depends_on"] == ["app"]
    assert "8443:8443" in compose["services"]["nginx"]["ports"]


def test_env_example_does_not_contain_secret_values():
    env_example = Path(".env.example").read_text(encoding="utf-8")

    assert "sk-" not in env_example
    assert "OPENAI_API_KEY=" in env_example
