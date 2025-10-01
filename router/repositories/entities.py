class ResolutionEntities:

    RESOLVED = 0
    UNRESOLVED = 1
    IN_PROGRESS = 2
    UNCLASSIFIED = 3

    def resolution_mapping(self, resolution_status: int) -> int:
        resolution_choices = [
            (self.RESOLVED, "Resolved"),
            (self.UNRESOLVED, "Unresolved"),
            (self.IN_PROGRESS, "In Progress"),
            (self.UNCLASSIFIED, "Unclassified")
        ]

        return resolution_choices[resolution_status]
