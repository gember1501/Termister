from __future__ import annotations

import argparse
import os

from .ui.app import TermisterApp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="termister",
        description="Magister in je terminal: rooster, cijfers en huiswerk/toetsen via de Magister API.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rich", dest="rich", action="store_true", help="gebruik de Rich-versie (eenvoudigere terminal-GUI) (standaard)")
    group.add_argument("--textual", dest="textual", action="store_true", help="gebruik de Textual-versie (tabbed terminal-UI)")
    parser.add_argument("--demo", action="store_true", help="starten met voorbeelddata (zonder inloggen)")
    parser.add_argument("--school", default=os.environ.get("MAGISTER_SCHOOL"), help="schoolnaam")
    parser.add_argument("--username", default=os.environ.get("MAGISTER_USERNAME"), help="gebruikersnaam")
    parser.add_argument(
        "--password",
        default=os.environ.get("MAGISTER_PASSWORD"),
        help="wachtwoord (liever via de login-UI invoeren)",
    )
    parser.add_argument("--no-cache", action="store_true", help="opgeslagen sessie negeren")
    parser.add_argument("--no-credentials", action="store_true", help="laadt geen opgeslagen school/gebruikersnaam uit de configuratie")
    args = parser.parse_args(argv)

    # Start the chosen UI. Default to Rich unless --textual is specified.
    if args.textual:
        app = TermisterApp(
            demo=args.demo,
            school=args.school,
            username=args.username,
            password=args.password,
            use_cache=not args.no_cache,
            use_saved_credentials=(not args.no_credentials),
        )
        app.run()
        return

    # Default / fallback: Rich UI
    from .rich_app import main as rich_main

    rich_main(
        demo=args.demo,
        school=args.school,
        username=args.username,
        password=args.password,
        use_cache=not args.no_cache,
        use_saved_credentials=(not args.no_credentials),
    )
    return
