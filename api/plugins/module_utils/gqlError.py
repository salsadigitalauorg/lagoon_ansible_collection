class ResourceError(Exception):
    """
    Raised when errors have been accumulated during an operation.

    Attributes:
        errors -- a list of error messages
    """

    def __init__(self, errors: list, message: str):
        self.errors = errors
        self.message = message
        super().__init__(self.message)
