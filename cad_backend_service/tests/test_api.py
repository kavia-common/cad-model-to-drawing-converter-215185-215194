import io
import time

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

TEST_EMAIL = "user@example.com"
TEST_PASS = "password123"


def auth_headers():
    # register (idempotent)
    client.post("/auth/register", json={"email": TEST_EMAIL, "password": TEST_PASS})
    # login
    resp = client.post("/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASS}, headers={"content-type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"] == "Healthy"


def test_register_and_login():
    # Register new user with random email
    email = f"user_{int(time.time())}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": TEST_PASS})
    assert r.status_code in (200, 400)  # may already exist if rerun
    r = client.post("/auth/login", data={"username": email, "password": TEST_PASS}, headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body


def test_upload_convert_and_downloads():
    headers = auth_headers()
    # Create a dummy STEP file content
    file_content = b"ISO-10303-21;\nEND-ISO-10303-21;"
    files = {"file": ("model.step", io.BytesIO(file_content), "application/octet-stream")}
    r = client.post("/files/upload", files=files, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    job_id = data["job_id"]
    assert data["status"] in ("PENDING", "PROCESSING", "COMPLETED")

    # Poll the job until completed (stubbed conversion is fast)
    for _ in range(30):
        j = client.get(f"/jobs/{job_id}", headers=headers)
        assert j.status_code == 200
        status = j.json()["status"]
        if status == "COMPLETED":
            break
        time.sleep(0.2)
    assert status == "COMPLETED"

    # Downloads
    pdf = client.get(f"/downloads/{job_id}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")

    dxf = client.get(f"/downloads/{job_id}/dxf", headers=headers)
    assert dxf.status_code == 200
    assert "application/dxf" in dxf.headers["content-type"]

    preview = client.get(f"/downloads/{job_id}/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/png")


def test_jobs_list():
    headers = auth_headers()
    r = client.get("/jobs", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
