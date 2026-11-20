import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.events import Event, EventBus, get_bus
from app.main import create_app


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish(self, event: Event) -> None:
        self.events.append(event)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite://", api_token=None)


@pytest.fixture
def published() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture
def client(settings, published):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_bus] = lambda: EventBus([published])
    with TestClient(app) as c:
        yield c


@pytest.fixture
def vehicle(client) -> dict:
    r = client.post(
        "/api/v1/vehicles",
        json={"name": "Golf", "make": "VW", "license_plate": "AB-123-C", "odometer_km": 50000},
    )
    assert r.status_code == 201, r.text
    return r.json()
