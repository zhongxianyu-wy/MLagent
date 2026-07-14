from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_setup_directories_exist():
    expected_dirs = [
        "src/agent",
        "src/aide_adapter",
        "src/data_intake",
        "src/evaluation",
        "src/frontend_api",
        "src/memory",
        "src/provider",
        "src/research",
        "src/skill_bridge",
        "src/tracking",
        "src/training/scripts",
        "src/ui",
        "tests/contract",
        "tests/integration",
        "tests/unit",
        "tests/fixtures",
        "experiments/data",
        "experiments/standardized",
        "experiments/models",
        "experiments/outputs",
        "db",
    ]

    missing = [path for path in expected_dirs if not (ROOT / path).is_dir()]

    assert missing == []


def test_pyproject_declares_runtime_and_test_dependencies():
    pyproject_path = ROOT / "pyproject.toml"

    assert pyproject_path.is_file()

    content = pyproject_path.read_text()

    assert 'name = "mlagent-v3"' in content
    assert 'requires-python = ">=3.11"' in content

    for package in [
        "pandas",
        "numpy",
        "scikit-learn",
        "xgboost",
        "mem0ai",
        "chromadb",
        "mlflow",
        "nbformat",
        "streamlit",
    ]:
        assert package in content

    for package in ["pytest", "pytest-cov"]:
        assert package in content


def test_environment_template_contains_required_settings():
    env_example = ROOT / ".env.example"

    assert env_example.is_file()

    content = env_example.read_text()
    for key in [
        "MLAGENT_LLM_BASE_URL=",
        "MLAGENT_LLM_API_PROTOCOL=",
        "MLAGENT_LLM_API_KEY_ENV=",
        "MLAGENT_LLM_MODEL=",
        "MLAGENT_LLM_SMALL_MODEL=",
        "MLFLOW_TRACKING_URI=",
        "CHROMA_DB_PATH=",
        "SQLITE_DB_PATH=",
        "ANTHROPIC_BASE_URL=",
        "ANTHROPIC_API_KEY=",
        "ANTHROPIC_MODEL=",
        "API_TIMEOUT_MS=",
    ]:
        assert key in content


def test_gitignore_excludes_local_data_and_secrets():
    gitignore = ROOT / ".gitignore"

    assert gitignore.is_file()

    content = gitignore.read_text()
    for pattern in [
        ".env",
        "db/",
        "experiments/data/",
        "experiments/standardized/",
        "experiments/models/",
        "experiments/outputs/",
        "db/chroma/",
    ]:
        assert pattern in content


def test_fixtures_readme_exists():
    assert (ROOT / "tests/fixtures/README.md").is_file()
