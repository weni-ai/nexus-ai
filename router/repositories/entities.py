class ResolutionEntities:

    RESOLVED = 0
    UNRESOLVED = 1
    IN_PROGRESS = 2
    UNCLASSIFIED = 3

    @staticmethod
    def resolution_mapping(resolution_status: int) -> tuple:
        resolution_choices = {
            ResolutionEntities.RESOLVED: (ResolutionEntities.RESOLVED, "Resolved"),
            ResolutionEntities.UNRESOLVED: (ResolutionEntities.UNRESOLVED, "Unresolved"),
            ResolutionEntities.IN_PROGRESS: (ResolutionEntities.IN_PROGRESS, "In Progress"),
            ResolutionEntities.UNCLASSIFIED: (ResolutionEntities.UNCLASSIFIED, "Unclassified")
        }

        return resolution_choices.get(resolution_status, (ResolutionEntities.UNCLASSIFIED, "Unclassified"))
