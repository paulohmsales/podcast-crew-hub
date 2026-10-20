"""Admin commands, run inside the container:

    python -m app.cli add-member "Paulo" paulo@x.com --admin
    python -m app.cli first-access "Paulo" [--email paulo@x.com]
    python -m app.cli list
    python -m app.cli import-feed https://anchor.fm/s/.../podcast/rss

Members without a password set one on their first login with their email;
first-access clears a password (and can set the email) to allow that again.
"""

import argparse

from sqlalchemy import select

from app import auth
from app.db import SessionLocal
from app.models import Member


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-member", help="create a member (password set on first login)")
    add.add_argument("name")
    add.add_argument("email")
    add.add_argument("--admin", action="store_true")
    reopen = sub.add_parser("first-access", help="clear a member's password so their next login sets it")
    reopen.add_argument("name")
    reopen.add_argument("--email")
    sub.add_parser("list", help="list members")
    imp = sub.add_parser("import-feed", help="create published episodes from the podcast RSS feed")
    imp.add_argument("url")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.cmd == "list":
            for m in db.scalars(select(Member).order_by(Member.name)):
                state = "ok" if m.password_hash else "primeiro acesso"
                print(f"{m.name:20} {m.email or '-':32} {state:16} {'admin' if m.is_admin else ''}")
            return
        if args.cmd == "import-feed":
            from app import feed

            admin = db.scalar(select(Member).where(Member.is_admin.is_(True)).order_by(Member.id))
            if not admin:
                raise SystemExit("needs an admin member to own the imported episodes")
            episodes = feed.parse(feed.fetch(args.url))
            created, skipped = feed.import_episodes(db, episodes, admin)
            print(f"{len(episodes)} in feed: {created} created, {skipped} already there")
            return
        if args.cmd == "add-member":
            member = Member(name=args.name, email=auth.normalize_email(args.email), is_admin=args.admin)
            db.add(member)
        else:
            member = db.scalar(select(Member).where(Member.name == args.name))
            if not member:
                raise SystemExit(f"no member named {args.name!r}")
            if args.email:
                member.email = auth.normalize_email(args.email)
            auth.clear_password(db, member)
        db.commit()
        print(f"{member.name} <{member.email}>: next login with this email sets the password")


if __name__ == "__main__":
    main()
