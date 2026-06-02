"""Shared product visibility tests.

Asserts that:
1. Global products (owner_id IS NULL) are visible to both users.
2. A private product created by Alice is invisible to Bob
   in autocomplete, list, search, and detail endpoints.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.api.dependencies import get_read_session, get_session
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import Product, ProductAlias, User
from glucotracker.infra.db.session import GlucotrackerSession
from glucotracker.infra.security import hash_password, issue_access_token
from glucotracker.main import app

TEST_JWT_SECRET = "test-jwt-secret-for-shared-products-32c"


@pytest.fixture
def _shared_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Generator[dict]:
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    monkeypatch.setenv("PHOTO_STORAGE_DIR", str(tmp_path / "photos"))
    monkeypatch.setenv("ACTIVITY_LOG_DIR", str(tmp_path / "activity_logs"))
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=GlucotrackerSession,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )

    seed = session_factory()
    alice = User(
        username="alice",
        password_hash=hash_password("alice-pass"),
        role=UserRole.gluco,
    )
    bob = User(
        username="bob",
        password_hash=hash_password("bob-pass"),
        role=UserRole.food,
    )
    seed.add_all([alice, bob])
    seed.commit()
    alice_id = alice.id
    bob_id = bob.id

    global_product = Product(
        owner_id=None,
        name="Global Oatmeal",
        brand="Global Brand",
        barcode="1111111111",
        source_kind="manual",
        carbs_per_100g=60,
        protein_per_100g=12,
        fat_per_100g=7,
        kcal_per_100g=350,
    )
    alice_product = Product(
        owner_id=alice_id,
        name="Alice Private Cereal",
        brand="Alice Brand",
        barcode="2222222222",
        source_kind="manual",
        carbs_per_100g=70,
        protein_per_100g=10,
        fat_per_100g=5,
        kcal_per_100g=365,
    )
    seed.add_all([global_product, alice_product])
    seed.flush()
    global_alias = ProductAlias(
        owner_id=None,
        product_id=global_product.id,
        alias="oatmeal",
    )
    alice_alias = ProductAlias(
        owner_id=alice_id,
        product_id=alice_product.id,
        alias="private cereal",
    )
    seed.add_all([global_alias, alice_alias])
    seed.commit()
    global_pid = global_product.id
    alice_pid = alice_product.id
    seed.close()

    last_user: dict[str, UUID] = {}

    def _override_session() -> Generator[Session]:
        uid = last_user.get("id", alice_id)
        s = session_factory()
        s.info["current_user_id"] = uid
        try:
            yield s
        finally:
            s.close()

    def _override_read_session() -> Generator[Session]:
        uid = last_user.get("id", alice_id)
        s = session_factory()
        s.info["read_only"] = True
        s.info["current_user_id"] = uid
        try:
            yield s
        finally:
            s.rollback()
            s.close()

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_read_session] = _override_read_session

    with TestClient(app) as client:
        alice_headers = {
            "Authorization": f"Bearer {issue_access_token(alice_id, UserRole.gluco)}"
        }
        bob_headers = {
            "Authorization": f"Bearer {issue_access_token(bob_id, UserRole.food)}"
        }
        last_user["id"] = alice_id

        yield {
            "client": client,
            "engine": engine,
            "session_factory": session_factory,
            "alice_id": alice_id,
            "bob_id": bob_id,
            "alice_headers": alice_headers,
            "bob_headers": bob_headers,
            "global_product_id": global_pid,
            "alice_product_id": alice_pid,
        }

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def _set_user(env: dict, user: str) -> None:
    env["client"].headers.update(
        env["alice_headers"] if user == "alice" else env["bob_headers"]
    )


class TestGlobalProductsVisible:
    """Global products (owner_id NULL) must be visible to all users."""

    @pytest.fixture(autouse=True)
    def _setup(self, _shared_env):
        self.env = _shared_env
        self.client = _shared_env["client"]
        self.global_id = _shared_env["global_product_id"]
        self.alice_product_id = _shared_env["alice_product_id"]

    def test_alice_sees_global_in_list(self):
        r = self.client.get("/products", headers=self.env["alice_headers"])
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.global_id) in ids

    def test_bob_sees_global_in_list(self):
        r = self.client.get("/products", headers=self.env["bob_headers"])
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.global_id) in ids

    def test_alice_sees_global_in_search(self):
        r = self.client.get(
            "/products/search",
            params={"q": "Oatmeal"},
            headers=self.env["alice_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.global_id) in ids

    def test_bob_sees_global_in_search(self):
        r = self.client.get(
            "/products/search",
            params={"q": "Oatmeal"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.global_id) in ids

    def test_alice_sees_global_detail(self):
        r = self.client.get(
            f"/products/{self.global_id}", headers=self.env["alice_headers"]
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Global Oatmeal"

    def test_bob_sees_global_detail(self):
        r = self.client.get(
            f"/products/{self.global_id}", headers=self.env["bob_headers"]
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Global Oatmeal"

    def test_alice_sees_global_in_autocomplete(self):
        r = self.client.get(
            "/autocomplete",
            params={"q": "oatmeal"},
            headers=self.env["alice_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.global_id) in ids

    def test_bob_sees_global_in_autocomplete(self):
        r = self.client.get(
            "/autocomplete",
            params={"q": "oatmeal"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.global_id) in ids

    def test_alice_sees_global_in_database_items(self):
        r = self.client.get(
            "/database/items", headers=self.env["alice_headers"]
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.global_id) in ids

    def test_bob_sees_global_in_database_items(self):
        r = self.client.get(
            "/database/items", headers=self.env["bob_headers"]
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.global_id) in ids


class TestPrivateProductIsolation:
    """Alice's private product must be invisible to Bob."""

    @pytest.fixture(autouse=True)
    def _setup(self, _shared_env):
        self.env = _shared_env
        self.client = _shared_env["client"]
        self.alice_product_id = _shared_env["alice_product_id"]
        self.alice_id = _shared_env["alice_id"]

    def test_bob_does_not_see_alice_product_in_list(self):
        r = self.client.get("/products", headers=self.env["bob_headers"])
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.alice_product_id) not in ids

    def test_alice_sees_own_product_in_list(self):
        r = self.client.get("/products", headers=self.env["alice_headers"])
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.alice_product_id) in ids

    def test_bob_does_not_see_alice_product_in_search(self):
        r = self.client.get(
            "/products/search",
            params={"q": "Private Cereal"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.alice_product_id) not in ids

    def test_alice_sees_own_product_in_search(self):
        r = self.client.get(
            "/products/search",
            params={"q": "Private Cereal"},
            headers=self.env["alice_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.alice_product_id) in ids

    def test_bob_gets_404_on_alice_product_detail(self):
        r = self.client.get(
            f"/products/{self.alice_product_id}",
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 404

    def test_alice_gets_own_product_detail(self):
        r = self.client.get(
            f"/products/{self.alice_product_id}",
            headers=self.env["alice_headers"],
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Alice Private Cereal"

    def test_bob_does_not_see_alice_product_in_autocomplete(self):
        r = self.client.get(
            "/autocomplete",
            params={"q": "private cereal"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.alice_product_id) not in ids

    def test_alice_sees_own_product_in_autocomplete(self):
        r = self.client.get(
            "/autocomplete",
            params={"q": "private cereal"},
            headers=self.env["alice_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.alice_product_id) in ids

    def test_bob_does_not_see_alice_product_in_database_items(self):
        r = self.client.get(
            "/database/items", headers=self.env["bob_headers"]
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.alice_product_id) not in ids

    def test_alice_sees_own_product_in_database_items(self):
        r = self.client.get(
            "/database/items", headers=self.env["alice_headers"]
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert str(self.alice_product_id) in ids

    def test_bob_cannot_patch_alice_product(self):
        r = self.client.patch(
            f"/products/{self.alice_product_id}",
            json={"name": "hacked"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 404

    def test_bob_cannot_delete_alice_product(self):
        r = self.client.delete(
            f"/products/{self.alice_product_id}",
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 404

    def test_bob_cannot_see_alice_product_by_barcode(self):
        r = self.client.get(
            "/products/search",
            params={"q": "2222222222"},
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert str(self.alice_product_id) not in ids

    def test_bob_cannot_upload_image_for_alice_product(self):
        r = self.client.post(
            f"/products/{self.alice_product_id}/image",
            headers=self.env["bob_headers"],
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert r.status_code == 404

    def test_bob_cannot_get_alice_product_image(self):
        r = self.client.get(
            f"/products/{self.alice_product_id}/image/file",
            headers=self.env["bob_headers"],
        )
        assert r.status_code == 404
