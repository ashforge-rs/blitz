from typing import TYPE_CHECKING

from todo_app.kernel import Actor

if TYPE_CHECKING:
    from context import RequestContext


def request_actor(ctx: RequestContext, user_id: str | None = None) -> Actor:
    """The use-case :class:`Actor` for the current HTTP request."""
    return Actor(
        user_id=user_id,
        correlation_id=ctx.request_id,
        client_address=ctx.remote_addr,
        entrypoint=ctx.path,
    )
