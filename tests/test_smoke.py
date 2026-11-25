def test_package_imports():
    import jobgate

    assert jobgate is not None


def test_package_exposes_version():
    import jobgate

    assert jobgate.__version__ == "0.2.0"


def test_package_version_matches_pyproject():
    import tomllib
    from pathlib import Path

    import jobgate

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert declared == jobgate.__version__
