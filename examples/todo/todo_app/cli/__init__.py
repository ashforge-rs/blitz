"""Command-line driver for the todo app: the same use cases as HTTP, without a web stack.

    python -m todo_app.cli register --email ada@example.com --name Ada
    TODO_API_TOKEN=tdo_... python -m todo_app.cli create-todo --title "Buy milk"

Nothing here imports FastAPI, Starlette or the HTTP adapters; a test enforces it.
"""
