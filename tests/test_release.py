import runpy
from datetime import datetime, timedelta, timezone

next_tag = runpy.run_path("bin/create-release")["next_tag"]


def test_first_release_of_utc_day_starts_at_zero():
    assert next_tag(["v2026.11.13-9"], datetime(2026, 11, 14, tzinfo=timezone.utc)) == "v2026.11.14-0"


def test_release_sequence_uses_largest_suffix_and_utc_date():
    local = datetime(2026, 11, 13, 23, 30, tzinfo=timezone(timedelta(hours=-7)))
    tags = ["v2026.11.14-0", "v2026.11.14-2", "v2026.11.14-10", "v2026.11.14-preview", "v2026.11.13-99"]
    assert next_tag(tags, local) == "v2026.11.14-11"
