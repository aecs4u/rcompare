"""Entry point for running teczka as a module.

Supports CLI arguments via typer (optional dependency).
Falls back to plain argparse if typer is not installed.
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    try:
        import typer

        app = typer.Typer(add_completion=False)

        @app.command()
        def run(
            left: str = typer.Argument(None, help="Left path to compare"),
            right: str = typer.Argument(None, help="Right path to compare"),
            log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
            log_file: str = typer.Option(None, "--log-file", help="Log to file"),
        ) -> None:
            from teczka.app import launch

            launch(left=left, right=right, log_level=log_level, log_file=log_file)

        app()
    except ImportError:
        parser = argparse.ArgumentParser(description="Teczka - RCompare GUI")
        parser.add_argument("left", nargs="?", help="Left path to compare")
        parser.add_argument("right", nargs="?", help="Right path to compare")
        parser.add_argument("--log-level", default="INFO", help="Log level")
        parser.add_argument("--log-file", default=None, help="Log to file")
        args = parser.parse_args()

        from teczka.app import launch

        launch(
            left=args.left,
            right=args.right,
            log_level=args.log_level,
            log_file=args.log_file,
        )


if __name__ == "__main__":
    main()
