"""
One-off script to create the first admin user.
Run with:  python create_admin.py
"""
from getpass import getpass

from app import models
from app.database import SessionLocal, engine
from app.auth import hash_password

models.Base.metadata.create_all(bind=engine)


def main():
    db = SessionLocal()
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip()
    password = getpass("Admin password: ")

    if db.query(models.User).filter(models.User.email == email).first():
        print("A user with that email already exists.")
        return

    admin = models.User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role=models.UserRole.admin,
    )
    db.add(admin)
    db.commit()
    print(f"Admin user '{email}' created.")


if __name__ == "__main__":
    main()
