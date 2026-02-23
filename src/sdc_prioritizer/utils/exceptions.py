# =============================================================================
#   Domain Exceptions
# =============================================================================

class TestSuiteAlreadyExistsError(Exception):
    """Raised when a test suite with the given ID has already been uploaded."""
    pass


class TestSuiteNotFoundError(Exception):
    """Raised when a requested test suite does not exist."""
    pass


class PersistenceError(Exception):
    """Raised when a database operation fails unexpectedly."""
    pass

class StrategyNotFoundError(Exception):
    """Raised when the requested prioritization strategy does not exist."""
    pass