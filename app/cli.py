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

    @app.cli.command("seed-demo-full")
    def seed_demo_full_command() -> None:
        """Insert the complete fictional SIH demo dataset (idempotent)."""
        from app.services.full_seed import seed_demo_full

        with app.app_context():
            stats = seed_demo_full()

        lines = [
            "",
            "Demo seed complete:",
            f"Centres: {stats['centres']['new']} new, "
            f"{stats['centres']['existing']} existing",
            f"Crops: {stats['crops']['new']} new, "
            f"{stats['crops']['existing']} existing",
            f"Staff: {stats['staff']['new']} new, "
            f"{stats['staff']['existing']} existing",
            f"Farmers: {stats['farmers']['new']} new, "
            f"{stats['farmers']['existing']} existing",
            f"Slots: {stats['slots']['new']} new, "
            f"{stats['slots']['existing']} existing",
            f"Bookings: {stats['bookings']['new']} new, "
            f"{stats['bookings']['existing']} existing",
            f"Delays: {stats['delays']['new']} new, "
            f"{stats['delays']['existing']} existing",
            f"Notifications: {stats['notifications']['new']} new, "
            f"{stats['notifications']['total']} total",
            f"Procurement: {stats['procurements']['new']} new, "
            f"{stats['procurements']['existing']} existing",
            f"Payments: {stats['payments']['new']} new, "
            f"{stats['payments']['existing']} existing",
            f"Audit logs: {stats['audit_logs']['new']} new, "
            f"{stats['audit_logs']['total']} total",
            "",
        ]
        for line in lines:
            click.echo(line)