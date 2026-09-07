"""API testleri icin fixture'lar.

app.db.engine, DATABASE_URL varsayilaninda gercek bir Postgres'e isaret
ediyor (docker-compose'daki servis). Testler Postgres'in ayakta olmasina
BAGIMLI olmasin diye get_db bagimliligi, in-memory SQLite'a baglanan ayri
bir engine'e yonlendiriliyor -- app.main import edilirken app'in lifespan'i
tetiklenmedigi surece (TestClient `with` olarak KULLANILMADIGI surece
baslatma/kapanma olaylari calismaz) gercek engine'e hic dokunulmuyor.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Bilerek `with TestClient(app) as c:` DEGIL: context manager olarak
        # kullanmak lifespan'i (Base.metadata.create_all(bind=engine)) app.db'nin
        # GERCEK (Postgres'e isaret eden) engine'iyle tetikler ve Postgres ayakta
        # degilse testler bununla alakasiz bir sebeple patlar.
        test_client = TestClient(app)
        # Nokta/ArananArac icin POST ucu yok; testlerin bu tabloya dogrudan
        # yazabilmesi icin ayni (override edilen) engine'e bagli bir session
        # fabrikasi client'a iliniyor.
        test_client.SessionLocal = TestingSessionLocal
        yield test_client
    finally:
        app.dependency_overrides.clear()
