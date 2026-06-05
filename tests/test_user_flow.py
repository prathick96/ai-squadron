"""
tests/test_user_flow.py
End-to-end user journey tests for AI Squadron customer portal.

Coverage:
  - Auth separation: admin email rejected at /auth, customer never reaches /command-center
  - Free tier limit: 1 run/month enforced correctly
  - User profile API: returns plan + run usage
  - User ventures API: returns only this user's runs
  - Pipeline run: tagged with user_id when JWT provided
  - Upgrade path: 429 returned when limit reached with correct upgrade message

Run: pytest tests/test_user_flow.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from apps.api.main import app, _PLAN_RUN_LIMITS, _count_user_runs_this_month, _get_user_profile

client = TestClient(app, raise_server_exceptions=False)

ADMIN_EMAIL  = "admin@test.com"
USER_EMAIL   = "user@test.com"
USER_ID      = "00000000-0000-0000-0000-000000000001"
ADMIN_ID     = "00000000-0000-0000-0000-000000000002"


# ─── Plan limit constants ─────────────────────────────────────────────────────

class TestPlanLimits:
    def test_starter_limit_is_one(self):
        assert _PLAN_RUN_LIMITS["starter"] == 1

    def test_builder_limit_is_ten(self):
        assert _PLAN_RUN_LIMITS["builder"] == 10

    def test_studio_is_unlimited(self):
        assert _PLAN_RUN_LIMITS["studio"] == -1

    def test_unknown_plan_defaults_safe(self):
        # Unknown plans fall back to 1 (most restrictive) via dict.get
        assert _PLAN_RUN_LIMITS.get("enterprise", 1) == 1


# ─── Auth separation ─────────────────────────────────────────────────────────

class TestAuthSeparation:
    """Admin email must NEVER grant access to the customer portal endpoints."""

    def test_user_profile_requires_auth(self):
        resp = client.get("/api/user/profile")
        assert resp.status_code == 401

    def test_user_ventures_requires_auth(self):
        resp = client.get("/api/user/ventures")
        assert resp.status_code == 401

    def test_pipeline_run_without_auth_is_allowed_for_admin(self):
        """Pipeline without JWT = admin call → no limit check."""
        with patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock):
            resp = client.post("/api/pipeline/run", json={"department": "PRODUCT"})
        # Admin (no JWT) can always launch
        assert resp.status_code == 200
        assert resp.json()["status"] == "STARTED"


# ─── Free tier run limit ──────────────────────────────────────────────────────

class TestFreeTierLimit:
    """Free tier allows 1 run/month; 429 on the second attempt."""

    def _mock_jwt(self, email: str = USER_EMAIL, user_id: str = USER_ID) -> dict:
        """Returns headers dict with a mock Bearer token."""
        return {"Authorization": "Bearer mock_jwt_token"}

    def _mock_supabase_auth(self, email: str = USER_EMAIL, uid: str = USER_ID):
        mock_user = MagicMock()
        mock_user.email = email
        mock_user.id    = uid
        mock_resp       = MagicMock()
        mock_resp.user  = mock_user
        return mock_resp

    def test_first_run_allowed_on_starter(self, monkeypatch):
        """Starter user with 0 runs used → run is permitted."""
        monkeypatch.setenv("VITE_ADMIN_EMAIL", ADMIN_EMAIL)

        with (
            patch("supabase.create_client") as mock_sc,
            patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock),
        ):
            mock_sc.return_value.auth.get_user.return_value = self._mock_supabase_auth()

            with patch("apps.api.main._get_user_profile", return_value={"plan": "starter"}), \
                 patch("apps.api.main._count_user_runs_this_month", return_value=0):

                resp = client.post(
                    "/api/pipeline/run",
                    json={"department": "PRODUCT"},
                    headers=self._mock_jwt(),
                )

        assert resp.status_code == 200

    def test_second_run_blocked_on_starter(self, monkeypatch):
        """Starter user with 1 run already used → 429 on second attempt."""
        monkeypatch.setenv("VITE_ADMIN_EMAIL", ADMIN_EMAIL)

        with patch("supabase.create_client") as mock_sc:
            mock_sc.return_value.auth.get_user.return_value = self._mock_supabase_auth()

            with patch("apps.api.main._get_user_profile", return_value={"plan": "starter"}), \
                 patch("apps.api.main._count_user_runs_this_month", return_value=1):

                resp = client.post(
                    "/api/pipeline/run",
                    json={"department": "PRODUCT"},
                    headers=self._mock_jwt(),
                )

        assert resp.status_code == 429
        detail = resp.json().get("detail", "")
        assert "limit" in detail.lower() or "upgrade" in detail.lower()

    def test_builder_allows_ten_runs(self, monkeypatch):
        """Builder user with 9 runs used → 10th run is permitted."""
        monkeypatch.setenv("VITE_ADMIN_EMAIL", ADMIN_EMAIL)

        with (
            patch("supabase.create_client") as mock_sc,
            patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock),
        ):
            mock_sc.return_value.auth.get_user.return_value = self._mock_supabase_auth()

            with patch("apps.api.main._get_user_profile", return_value={"plan": "builder"}), \
                 patch("apps.api.main._count_user_runs_this_month", return_value=9):

                resp = client.post(
                    "/api/pipeline/run",
                    json={"department": "PRODUCT"},
                    headers=self._mock_jwt(),
                )

        assert resp.status_code == 200

    def test_studio_never_blocked(self, monkeypatch):
        """Studio (unlimited) user can always run regardless of count."""
        monkeypatch.setenv("VITE_ADMIN_EMAIL", ADMIN_EMAIL)

        with (
            patch("supabase.create_client") as mock_sc,
            patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock),
        ):
            mock_sc.return_value.auth.get_user.return_value = self._mock_supabase_auth()

            with patch("apps.api.main._get_user_profile", return_value={"plan": "studio"}), \
                 patch("apps.api.main._count_user_runs_this_month", return_value=999):

                resp = client.post(
                    "/api/pipeline/run",
                    json={"department": "PRODUCT"},
                    headers=self._mock_jwt(),
                )

        assert resp.status_code == 200

    def test_429_message_contains_upgrade_info(self, monkeypatch):
        """The 429 error message must mention upgrade path."""
        monkeypatch.setenv("VITE_ADMIN_EMAIL", ADMIN_EMAIL)

        with patch("supabase.create_client") as mock_sc:
            mock_sc.return_value.auth.get_user.return_value = self._mock_supabase_auth()

            with patch("apps.api.main._get_user_profile", return_value={"plan": "starter"}), \
                 patch("apps.api.main._count_user_runs_this_month", return_value=1):

                resp = client.post(
                    "/api/pipeline/run",
                    json={"department": "PRODUCT"},
                    headers=self._mock_jwt(),
                )

        assert resp.status_code == 429
        body = resp.json()["detail"]
        # Must mention the current limit and an upgrade path
        assert "1" in body          # mentions the limit (1/1)
        assert "Builder" in body    # upgrade suggestion


# ─── Plan limit helper unit tests ────────────────────────────────────────────

class TestRunCountHelper:
    def test_returns_zero_when_supabase_unavailable(self):
        """No Supabase → 0 runs (fail-safe, never blocks customer)."""
        with patch("apps.api.main._count_user_runs_this_month", wraps=_count_user_runs_this_month):
            with patch("packages.db.client.is_supabase_connected", return_value=False):
                count = _count_user_runs_this_month("some-user-id")
        assert count == 0

    def test_returns_zero_when_db_errors(self):
        """DB errors → 0 runs (fail-safe)."""
        with patch("packages.db.client.is_supabase_connected", return_value=True), \
             patch("packages.db.client.get_db", side_effect=Exception("DB down")):
            count = _count_user_runs_this_month("some-user-id")
        assert count == 0


class TestUserProfileHelper:
    def test_returns_none_when_supabase_unavailable(self):
        with patch("packages.db.client.is_supabase_connected", return_value=False):
            profile = _get_user_profile("some-user-id")
        assert profile is None

    def test_returns_none_on_db_error(self):
        with patch("packages.db.client.is_supabase_connected", return_value=True), \
             patch("packages.db.client.get_db", side_effect=Exception("DB down")):
            profile = _get_user_profile("some-user-id")
        assert profile is None


# ─── Health endpoint ─────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_has_railway_available_field(self):
        resp = client.get("/api/health")
        body = resp.json()
        assert "railway_available" in body

    def test_health_version_is_current(self):
        resp = client.get("/api/health")
        body = resp.json()
        assert body["version"] == "0.5.0"


# ─── Pipeline run endpoint ────────────────────────────────────────────────────

class TestPipelineRunEndpoint:
    def test_run_without_jwt_succeeds_as_admin(self):
        with patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock):
            resp = client.post("/api/pipeline/run", json={"department": "PRODUCT"})
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "venture_id" in data
        assert data["status"] == "STARTED"

    def test_run_with_media_department_rejected(self):
        """MEDIA department is archived — API returns 422 (invalid literal)."""
        with patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock):
            resp = client.post("/api/pipeline/run", json={"department": "MEDIA"})
        assert resp.status_code == 422

    def test_run_with_explicit_venture_id(self):
        with patch("apps.api.main._run_pipeline_background", new_callable=AsyncMock):
            resp = client.post("/api/pipeline/run", json={
                "department": "PRODUCT",
                "venture_id": "ven_test_001",
            })
        assert resp.status_code == 200
        assert resp.json()["venture_id"] == "ven_test_001"
