from router.route import get_language_codes


def test_get_language_codes_defaults_to_pt_if_unknown():
    assert get_language_codes("pt") == "português"
    assert get_language_codes("en") == "inglês"
    assert get_language_codes("unknown") == "português"
