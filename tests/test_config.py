from promptify.core.config import CaseConfig


def test_case_config_loading(test_sandbox):
    """Tests if CaseConfig correctly loads from config.json."""
    case_dir = test_sandbox["case"]
    config = CaseConfig(case_dir)
    assert config.name == "test_case"
    assert config.types == ["*"]


def test_ignore_spec(test_sandbox):
    """Tests if CaseConfig correctly compiles pathspec from .gitignore and .caseignore."""
    case_dir = test_sandbox["case"]
    demo_dir = test_sandbox["demo"]
    config = CaseConfig(case_dir)

    spec = config.get_ignore_spec(demo_dir)
    assert spec.match_file("secret.key")
    assert spec.match_file("test.log")
    assert spec.match_file(".git/config")
    assert not spec.match_file("app.py")
