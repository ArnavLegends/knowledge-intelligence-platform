"""Repository scaffold validation tests.

These tests verify that the project foundation (directories, configuration
files, and tooling) is in place. They do not test application logic.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DIRECTORIES = [
    ".github",
    "assets",
    "backend",
    "benchmarks",
    "configs",
    "datasets",
    "docker",
    "docs",
    "evaluation",
    "examples",
    "frontend",
    "paper",
    "research",
    "scripts",
    "tests",
]

EXPECTED_FILES = [
    ".env.example",
    ".gitignore",
    "LICENSE",
    "README.md",
    "pyproject.toml",
]


def test_expected_directories_exist() -> None:
    missing = [name for name in EXPECTED_DIRECTORIES if not (ROOT / name).is_dir()]
    assert not missing, f"Missing directories: {', '.join(missing)}"


def test_expected_files_exist() -> None:
    missing = [name for name in EXPECTED_FILES if not (ROOT / name).is_file()]
    assert not missing, f"Missing files: {', '.join(missing)}"


def test_github_workflow_exists() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file(), "Missing workflow: .github/workflows/ci.yml"


def test_directory_readmes_exist() -> None:
    directories_with_readmes = [
        "assets",
        "backend",
        "benchmarks",
        "configs",
        "datasets",
        "docker",
        "evaluation",
        "examples",
        "frontend",
        "paper",
        "research",
        "scripts",
        "tests",
    ]
    missing = [
        name
        for name in directories_with_readmes
        if not (ROOT / name / "README.md").is_file()
    ]
    assert not missing, f"Missing directory README files: {', '.join(missing)}"


def test_pyproject_declares_python_version() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "requires-python" in pyproject
    assert ">=3.11" in pyproject
