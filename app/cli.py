"""Admin commands, run inside the container:

    python -m app.cli add-member "Paulo" --admin
    python -m app.cli links
"""

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Member
from app.web import login_url, new_token


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-member", help="create a member and print their login link")
    add.add_argument("name")
    add.add_argument("--admin", action="store_true")
    add.add_argument("--phone")
    sub.add_parser("links", help="print every member's login link")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.cmd == "add-member":
            member = db.scalar(select(Member).where(Member.name == args.name))
            if not member:
                member = Member(name=args.name, token=new_token(), is_admin=args.admin, phone=args.phone)
                db.add(member)
                db.commit()
            print(f"{member.name}: {login_url(member)}")
        else:
            for member in db.scalars(select(Member).order_by(Member.name)):
                print(f"{member.name}{' (admin)' if member.is_admin else ''}: {login_url(member)}")


if __name__ == "__main__":
    main()
