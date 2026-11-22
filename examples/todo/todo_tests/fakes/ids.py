from todo_app.kernel import IdGenerator


class SequentialIds(IdGenerator):
    def __init__(self, prefix: str = "id") -> None:
        self._prefix = prefix
        self._next = 0

    def new_id(self) -> str:
        self._next += 1
        return f"{self._prefix}-{self._next}"
