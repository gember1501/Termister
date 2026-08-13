class TermisterError(Exception):
    """Basis-fout voor alles dat fout kan gaan in Termister."""


class LoginError(TermisterError):
    """Inloggen bij Magister is mislukt."""


class NotAuthenticatedError(TermisterError):
    """De sessie is verlopen of de token is ongeldig."""


class FetchError(TermisterError):
    """Gegevens konden niet worden opgehaald bij Magister."""
