"""Admin commands, run inside the container:

    python -m app.cli add-member "Paulo" --username paulo --email paulo@x.com --admin
    python -m app.cli reset-password paulo
    python -m app.cli list

Both add-member and reset-password print a new random password.
"""

import argparse

from sqlalchemy import select

from app import auth
from app.db import SessionLocal
from app.models import Member


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-member", help="create a member and print a password")
    add.add_argument("name")
    add.add_argument("--username", required=True)
    add.add_argument("--email")
    add.add_argument("--admin", action="store_true")
    reset = sub.add_parser("reset-password", help="set a new random password and print it")
    reset.add_argument("username")
    sub.add_parser("list", help="list members")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.cmd == "list":
            for m in db.scalars(select(Member).order_by(Member.name)):
                print(f"{m.username:15} {m.name:20} {m.email or '-':30} {'admin' if m.is_admin else ''}")
            return
        if args.cmd == "add-member":
            member = Member(
                name=args.name,
                username=auth.normalize_username(args.username),
                email=args.email.lower() if args.email else None,
                is_admin=args.admin,
            )
            db.add(member)
            db.flush()
        else:
            member = auth.find_member(db, args.username)
            if not member:
                raise SystemExit(f"no member {args.username!r}")
        password = auth.generate_password()
        auth.set_password(db, member, password)
        db.commit()
        print(f"{member.username}: {password}")


if __name__ == "__main__":
    main()
