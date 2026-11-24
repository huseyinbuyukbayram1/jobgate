def test_package_imports():
    import jobgate

    assert jobgate is not None


def test_package_exposes_version():
    import jobgate

    assert jobgate.__version__ == "0.1.0"
