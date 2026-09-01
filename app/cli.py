"""Custom Flask CLI commands (invoked with `flask <command>`)."""

import click


def register_cli(app) -> None:
    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Insert fictional demo centres and crops (idempotent)."""
        from app.services.seed import seed_demo

        with app.app_context():
            stats = seed_demo()
        click.echo(
            "Seeded demo data: "
            f"centres={stats['centres']} crops={stats['crops']}"
        )