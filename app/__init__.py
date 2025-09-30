"""Dash application factory and global layout."""

from .data import INITIAL_COMPANIES, INITIAL_PARAMETERS


def create_app():
    """Create and configure the Dash application instance."""
    from dash import Dash, dcc, html
    import dash

    app = Dash(
        __name__,
        use_pages=True,
        suppress_callback_exceptions=True,
        title="Кооперативная модель R&D",
    )

    app.layout = html.Div(
        [
            dcc.Location(id="url"),
            dcc.Store(id="companies-store", data=INITIAL_COMPANIES),
            dcc.Store(id="parameters-store", data=INITIAL_PARAMETERS),
            html.Header(
                [
                    html.H1("Кооперативная модель R&D — интерактивный дашборд"),
                    html.Nav(
                        [
                            html.A(
                                page["name"],
                                href=page["path"],
                                className="nav-link",
                            )
                            for page in dash.page_registry.values()
                            if page.get("path")
                        ],
                        className="nav",
                    ),
                ],
                className="app-header",
            ),
            html.Main(dash.page_container, className="app-main"),
        ],
        className="app",
    )

    return app


try:
    app = create_app()
    server = app.server
except ModuleNotFoundError:  # pragma: no cover - allows tests without Dash installed
    app = None
    server = None
