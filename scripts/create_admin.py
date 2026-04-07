from __future__ import annotations

import argparse
import asyncio
import random
import secrets
import string
import sys
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db.models import Role, User, UserRole
from db.session import AsyncSessionLocal
from services.auth import hash_password


PASSWORD_LENGTH = 24
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or update local admin user.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument("--full-name", default=None)
    return parser


def _generate_password(length: int = PASSWORD_LENGTH) -> str:
    if length < 4:
        raise ValueError("Password length must be at least 4 characters.")

    required_chars = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*-_"),
    ]
    remaining_chars = [secrets.choice(PASSWORD_ALPHABET) for _ in range(length - len(required_chars))]
    password_chars = required_chars + remaining_chars
    random.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


async def _get_role_id(session, name: str) -> int:
    role = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(name=name, description=f"{name} role")
        session.add(role)
        await session.flush()
    return role.id


async def _run(args: argparse.Namespace) -> None:
    generated_password = _generate_password()

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.username == args.username))).scalar_one_or_none()
        if user is None:
            user = User(
                username=args.username,
                email=args.email,
                full_name=args.full_name,
                password_hash=hash_password(generated_password),
                is_local=True,
                is_active=True,
            )
            session.add(user)
            await session.flush()
        else:
            user.email = args.email
            user.full_name = args.full_name
            user.password_hash = hash_password(generated_password)
            user.is_local = True
            user.is_active = True

        admin_role_id = await _get_role_id(session, "admin")
        analyst_role_id = await _get_role_id(session, "analyst")
        for role_id in (admin_role_id, analyst_role_id):
            existing = (
                await session.execute(
                    select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(UserRole(user_id=user.id, role_id=role_id))

        await session.commit()
        print(f"Admin user is ready: username={user.username} id={user.id}")
        print(f"Generated password: {generated_password}")


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
