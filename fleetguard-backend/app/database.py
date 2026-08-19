from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite database file will be created in the root of the backend directory
SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"

# connect_args={"check_same_thread": False} is required for SQLite in FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency generator for FastAPI routes to access the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()