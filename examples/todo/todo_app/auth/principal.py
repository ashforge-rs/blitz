from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller."""

    user_id: str

    def __str__(self) -> str:  # how audit events record the principal
        return self.user_id
