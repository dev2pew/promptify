"""Tests for case configuration and ignore parsing"""

from tests import conftest as test_conftest

from promptify.core.config import CaseConfig


def test_case_config_loading(test_sandbox):
    """CaseConfig should load values from `config.json`"""
    case_dir = test_sandbox["case"]
    config = CaseConfig(case_dir)
    assert config.name == "test_case"
    assert config.types == ["*"]


def test_ignore_spec(test_sandbox):
    """CaseConfig should compile a PathSpec from `.gitignore` and `.caseignore`"""
    case_dir = test_sandbox["case"]
    demo_dir = test_sandbox["demo"]
    config = CaseConfig(case_dir)

    spec = config.get_ignore_spec(demo_dir)
    assert spec.match_file("secret.key")
    assert spec.match_file("test.log")
    assert spec.match_file(".git/config")
    assert not spec.match_file("app.py")


def test_cleanup_test_sandbox_roots_removes_all_reserved_sandbox_dirs(test_sandbox):
    """Repo-local sandbox prefixes should be cleaned together after test runs"""
    cleanup_root = test_sandbox["root"] / "cleanup_lab"
    cleanup_root.mkdir(parents=True, exist_ok=True)
    sandbox_roots = (
        cleanup_root / "sandbox_check",
        cleanup_root / "sandbox_check2",
        cleanup_root / "sandbox_check3",
        cleanup_root / "sandbox_check4",
    )

    for root in sandbox_roots:
        (root / "demo").mkdir(parents=True, exist_ok=True)
        (root / "demo" / "app.py").write_text("print('x')\n", encoding="utf-8")

    test_conftest._cleanup_test_sandbox_roots(cleanup_root)

    assert all(not root.exists() for root in sandbox_roots)
