from consent_app.factory import create_consent_app

#: ASGI entry point: ``uvicorn consent_app.main:app``.
app = create_consent_app()
