from src.database import engine
from src.models.base import Base
from src.models.item import Item
from src.models.topic import Topic
from src.models.app_config import AppConfig
from src.models.follow import Follow
from src.models.rss import RssFeed

def init():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init()
