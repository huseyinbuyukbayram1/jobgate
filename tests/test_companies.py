from pathlib import Path

import pytest

from jobgate.companies import ConfigError, load_companies

REPO_ROOT = Path(__file__).parent.parent


def write(tmp_path, text):
    path = tmp_path / "companies.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_companies_and_defaults(tmp_path):
    cfg = load_companies(
        write(
            tmp_path,
            """
companies:
  - {name: Acme, ats: greenhouse, token: acme}
  - {name: Beta, ats: lever, token: beta, enabled: false}
""",
        )
    )
    assert [c.name for c in cfg.companies] == ["Acme", "Beta"]
    assert cfg.companies[0].enabled is True
    assert all(cfg.sources.values())  # every source defaults to on


def test_active_companies_skip_disabled_company_and_disabled_source(tmp_path):
    cfg = load_companies(
        write(
            tmp_path,
            """
sources: {lever: false}
companies:
  - {name: Acme, ats: greenhouse, token: acme}
  - {name: Beta, ats: lever, token: beta}
  - {name: Gamma, ats: ashby, token: gamma, enabled: false}
""",
        )
    )
    assert [c.name for c in cfg.active_companies()] == ["Acme"]


def test_unknown_ats_is_rejected_with_clear_message(tmp_path):
    with pytest.raises(ConfigError, match="workday"):
        load_companies(write(tmp_path, "companies:\n  - {name: A, ats: workday, token: a}\n"))


def test_missing_token_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="token"):
        load_companies(write(tmp_path, "companies:\n  - {name: A, ats: lever}\n"))


def test_duplicate_company_is_rejected(tmp_path):
    text = "companies:\n  - {name: A, ats: lever, token: a}\n  - {name: A2, ats: lever, token: a}\n"
    with pytest.raises(ConfigError, match="duplicate"):
        load_companies(write(tmp_path, text))


def test_unknown_source_name_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="workday"):
        load_companies(write(tmp_path, "sources: {workday: true}\ncompanies: []\n"))


def test_missing_file_and_bad_yaml_give_config_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_companies(tmp_path / "nope.yaml")
    with pytest.raises(ConfigError, match="YAML"):
        load_companies(write(tmp_path, "companies: [unclosed"))


def test_example_file_is_valid_and_has_ten_companies():
    cfg = load_companies(REPO_ROOT / "companies.example.yaml")
    assert len(cfg.companies) == 10
    assert {c.ats for c in cfg.companies} == {"greenhouse", "lever", "ashby"}


def test_region_defaults_to_global_and_eu_is_accepted_for_lever(tmp_path):
    cfg = load_companies(
        write(
            tmp_path,
            """
companies:
  - {name: Acme, ats: lever, token: acme}
  - {name: Beta, ats: lever, token: beta, region: eu}
""",
        )
    )
    assert [c.region for c in cfg.companies] == ["global", "eu"]


def test_region_eu_is_only_for_lever_and_unknown_regions_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="region"):
        load_companies(
            write(tmp_path, "companies:\n  - {name: A, ats: greenhouse, token: a, region: eu}\n")
        )
    with pytest.raises(ConfigError, match="region"):
        load_companies(
            write(tmp_path, "companies:\n  - {name: A, ats: lever, token: a, region: mars}\n")
        )


def test_the_same_lever_site_name_may_exist_on_both_hosts_but_not_twice_on_one(tmp_path):
    both = """
companies:
  - {name: A, ats: lever, token: same}
  - {name: A EU, ats: lever, token: same, region: eu}
"""
    assert len(load_companies(write(tmp_path, both)).companies) == 2
    twice = both.replace("same, region: eu", "same")
    with pytest.raises(ConfigError, match="duplicate"):
        load_companies(write(tmp_path, twice))
