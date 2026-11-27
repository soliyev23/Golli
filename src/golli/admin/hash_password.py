"""Admin parolining xeshini chiqaradi: python -m golli.admin.hash_password"""

import getpass

from golli.admin.auth import hash_password

if __name__ == "__main__":
    password = getpass.getpass("Yangi parol: ")
    if len(password) < 10:
        raise SystemExit("Parol kamida 10 belgi bo'lsin.")
    if getpass.getpass("Yana bir marta: ") != password:
        raise SystemExit("Parollar mos kelmadi.")
    print(f"ADMIN_PASSWORD_HASH={hash_password(password)}")
