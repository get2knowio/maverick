from __future__ import annotations


class MaverickError(Exception):
    """Base exception class for all Maverick-specific errors.

    This is the root of the Maverick exception hierarchy. All custom exceptions
    in the Maverick application should inherit from this class. This allows
    catching all Maverick-specific errors at CLI boundaries while letting
    system exceptions propagate naturally.

    Attributes:
        message: Human-readable error message describing what went wrong.

    Example:
        ```python
        try:
            # Maverick operations
            workflow.execute()
        except MaverickError as e:
            # Catch all Maverick errors at CLI boundary
            logger.error(f"Maverick error: {e.message}")
            sys.exit(1)
        ```
    """

    def __init__(self, message: str) -> None:
        """Initialize the MaverickError.

        Args:
            message: Human-readable error message.
        """
        self.message = message
        super().__init__(message)
