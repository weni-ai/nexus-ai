class ResolutionEntities:
    RESOLVED = 0
    UNRESOLVED = 1
    IN_PROGRESS = 2
    UNCLASSIFIED = 3
    HAS_CHAT_ROOM = 4

    @staticmethod
    def resolution_mapping(resolution_status: int) -> tuple:
        resolution_choices = {
            ResolutionEntities.RESOLVED: (ResolutionEntities.RESOLVED, "Resolved"),
            ResolutionEntities.UNRESOLVED: (ResolutionEntities.UNRESOLVED, "Unresolved"),
            ResolutionEntities.IN_PROGRESS: (ResolutionEntities.IN_PROGRESS, "In Progress"),
            ResolutionEntities.UNCLASSIFIED: (ResolutionEntities.UNCLASSIFIED, "Unclassified"),
            ResolutionEntities.HAS_CHAT_ROOM: (ResolutionEntities.HAS_CHAT_ROOM, "Has Chat Room"),
        }

        return resolution_choices.get(resolution_status, (ResolutionEntities.UNCLASSIFIED, "Unclassified"))

    @staticmethod
    def convert_resolution_string_to_int(resolution_string: str) -> int:
        resolution_mapping = {
            "resolved": ResolutionEntities.RESOLVED,
            "unresolved": ResolutionEntities.UNRESOLVED,
            "in progress": ResolutionEntities.IN_PROGRESS,
            "unclassified": ResolutionEntities.UNCLASSIFIED,
            "has chat room": ResolutionEntities.HAS_CHAT_ROOM,
        }
        return resolution_mapping.get(resolution_string.lower(), ResolutionEntities.IN_PROGRESS)
