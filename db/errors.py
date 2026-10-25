"""Errors the db functions raise; the routes turn them into 404 and 409 responses."""


class NotFound(LookupError):
    """No such row. str(e) names what is missing: person, face, photo, voice or fact."""


class Conflict(Exception):
    """A uniqueness rule was broken. The message is shown to the family member."""
