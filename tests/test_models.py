from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jobgate.htmltext import html_to_text
from jobgate.models import Job


def make_job(**overrides):
    data = {
        "company": "Acme",
        "title": "Junior Backend Engineer",
        "location": "Berlin, Germany",
        "description": "Build APIs.",
        "url": "https://example.com/jobs/1",
        "posted_at": datetime(2026, 1, 5, tzinfo=UTC),
        "ats": "greenhouse",
        "ats_job_id": "1",
    }
    data.update(overrides)
    return Job(**data)


def test_job_accepts_valid_data():
    job = make_job()
    assert job.company == "Acme"
    assert job.ats == "greenhouse"


def test_job_date_and_location_are_optional():
    job = make_job(posted_at=None, location="")
    assert job.posted_at is None
    assert job.location == ""


def test_job_rejects_unknown_ats():
    with pytest.raises(ValidationError):
        make_job(ats="workday")


def test_job_requires_title_and_id():
    with pytest.raises(ValidationError):
        make_job(title="")
    with pytest.raises(ValidationError):
        make_job(ats_job_id="")


def test_job_key_is_unique_per_ats_company_and_id():
    assert make_job().key == "greenhouse:Acme:1"


def test_html_to_text_strips_tags_and_keeps_paragraph_breaks():
    text = html_to_text("<p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul>")
    assert text == "Hello world\nOne\nTwo"


def test_html_to_text_unescapes_escaped_html():
    # Greenhouse returns HTML encoded as entities
    assert html_to_text("&lt;p&gt;Fish &amp;amp; chips&lt;/p&gt;") == "Fish & chips"


def test_html_to_text_ignores_script_and_style():
    assert html_to_text("<style>p{}</style><p>Hi</p><script>x()</script>") == "Hi"


def test_html_to_text_handles_empty_and_none():
    assert html_to_text("") == ""
    assert html_to_text(None) == ""
