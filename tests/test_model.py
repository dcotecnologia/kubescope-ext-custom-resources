from datetime import UTC, datetime

from kubescope.custom_resources.model import (
    FAILING,
    SYNCED,
    UNKNOWN,
    WARNING,
    ExternalSecret,
    format_interval,
    last_sync_age,
    parse,
)


def test_parse_reads_the_sync_of_each_item_sorted(item) -> None:
    document = {
        "items": [
            item("b", "z", ready="False", reason="SecretSyncedError"),
            item("a", "z"),
            {"metadata": {}},  # no name: left out
            {"metadata": {"name": "bare"}},  # nothing else known
        ]
    }

    secrets = parse(document, "v1")

    assert [s.key for s in secrets] == [("default", "bare"), ("z", "a"), ("z", "b")]
    bare, synced, failing = secrets
    assert (bare.state, bare.ready, bare.store_kind, bare.target) == (
        UNKNOWN,
        "Unknown",
        "SecretStore",
        "bare",
    )
    assert (synced.state, synced.store, synced.target) == (SYNCED, "vault", "a-secret")
    assert (synced.version, synced.refresh_interval) == ("v1", "1h")
    assert (failing.state, failing.reason, failing.message) == (
        FAILING,
        "SecretSyncedError",
        "m",
    )


def test_a_secret_the_operator_deleted_is_a_warning_though_ready(item) -> None:
    (secret,) = parse({"items": [item("a", reason="SecretDeleted")]}, "v1")

    assert secret.ready == "True" and secret.state == WARNING


def test_parse_of_an_empty_document_is_empty() -> None:
    assert parse({}, "v1") == []


def _secret(refresh_time: str) -> ExternalSecret:
    return ExternalSecret(
        "ns", "a", "v1", "", "", "a", "True", "", "", "", refresh_time
    )


def test_the_age_of_the_last_sync() -> None:
    now = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)

    assert last_sync_age(_secret("2026-01-01T00:00:00Z"), now) == "5m"
    assert last_sync_age(_secret(""), now) == ""


def test_a_refresh_interval_is_said_like_the_ages_of_the_lists() -> None:
    assert format_interval("24h0m0s") == "1d"
    assert format_interval("24h") == "1d"
    assert format_interval("1h") == "1h"
    assert format_interval("1h30m") == "1h30m"
    assert format_interval("90s") == "1m"
    assert format_interval("45s") == "45s"
    assert format_interval("1.5h") == "1h30m"
    assert format_interval("500ms") == "0s"
    assert format_interval("0") == "0s"


def test_what_is_not_a_duration_is_shown_as_it_came() -> None:
    assert format_interval("") == ""
    assert format_interval("soon") == "soon"
    assert format_interval("1h later") == "1h later"
