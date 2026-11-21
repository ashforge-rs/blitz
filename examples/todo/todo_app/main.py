from todo_app.factory import create_todo_app

#: ASGI entry point: ``uvicorn todo_app.main:app``.
app = create_todo_app()
