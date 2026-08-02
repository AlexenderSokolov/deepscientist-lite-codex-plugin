class ControlPlaneError(RuntimeError):
    """Base class for fail-closed control-plane errors."""


class FenceRejected(ControlPlaneError):
    """A stale lease owner attempted a domain mutation."""


class LeaseBusy(ControlPlaneError):
    """A different owner still holds a live lease."""


class IntegrityIncident(ControlPlaneError):
    """A stable identity was reused with conflicting content."""


class MigrationRejected(ControlPlaneError):
    """An existing database cannot be migrated without guessing."""


class ReceiptConflict(IntegrityIncident):
    """A write-once receipt identity has different bytes."""
