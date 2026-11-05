from src.database import engine
from src.db_migrate import upgrade


def init():
    print("Creating / upgrading database schema...")
    applied = upgrade(engine)
    print(f"Schema ready. Added: {applied or 'nothing new'}")


if __name__ == "__main__":
    init()
