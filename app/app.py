"""Convenience entry-point for running the Dash development server."""

from . import app, create_app


if __name__ == "__main__":
    dash_app = app or create_app()
    dash_app.run_server(debug=True)
