from __future__ import annotations


def register_views(app):
    from .clone_voice_view import bp as clone_voice_bp

    if "clone_voice_view" not in app.blueprints:
        app.register_blueprint(clone_voice_bp)
