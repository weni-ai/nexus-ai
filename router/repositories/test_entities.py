from router.repositories.entities import ResolutionEntities


def test_resolution_mapping_known_and_unknown():
    assert ResolutionEntities.resolution_mapping(ResolutionEntities.RESOLVED) == (
        ResolutionEntities.RESOLVED,
        "Resolved",
    )
    assert ResolutionEntities.resolution_mapping(999) == (
        ResolutionEntities.UNCLASSIFIED,
        "Unclassified",
    )


def test_convert_resolution_string_to_int_cases():
    assert ResolutionEntities.convert_resolution_string_to_int("resolved") == ResolutionEntities.RESOLVED
    assert ResolutionEntities.convert_resolution_string_to_int("UNRESOLVED") == ResolutionEntities.UNRESOLVED
    assert ResolutionEntities.convert_resolution_string_to_int("has chat room") == ResolutionEntities.HAS_CHAT_ROOM
    assert ResolutionEntities.convert_resolution_string_to_int("unknown") == ResolutionEntities.IN_PROGRESS
