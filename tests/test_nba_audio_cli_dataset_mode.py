from mentions_sports_poller.nba_link_scout.audio_cli import _resolve_dataset_mode


def test_resolve_dataset_mode_auto_without_terms() -> None:
    assert _resolve_dataset_mode(mode_arg="auto", has_terms_arg=False) == "game"


def test_resolve_dataset_mode_auto_with_terms() -> None:
    assert _resolve_dataset_mode(mode_arg="auto", has_terms_arg=True) == "term"


def test_resolve_dataset_mode_explicit() -> None:
    assert _resolve_dataset_mode(mode_arg="both", has_terms_arg=False) == "both"
