from __future__ import annotations

from fastapi.testclient import TestClient


def test_welcome_screen_when_no_projects(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "Zerqon Spider" in res.text
    assert "Crawl Deeper. Discover More." in res.text
    assert res.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in res.headers["content-security-policy"]


def test_create_project_flow(client: TestClient) -> None:
    res = client.post(
        "/projects/new",
        data={"name": "Demo", "start_url": "example.com", "max_urls": "100", "render_mode": "standard"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    location = res.headers["location"]
    page = client.get(location)
    assert page.status_code == 200
    assert "https://example.com/" in page.text
    assert client.get("/").status_code == 200  # dashboard artık veriyle açılır
    assert "Demo" in client.get("/projects").text


def test_invalid_project_input_shows_errors(client: TestClient) -> None:
    res = client.post("/projects/new", data={"name": "", "start_url": "ftp://x", "exclude_patterns": "(unclosed"})
    assert res.status_code == 422
    assert "invalid" in res.text


def test_xss_in_project_name_is_escaped(client: TestClient) -> None:
    payload = "<script>alert(1)</script>"
    res = client.post("/projects/new", data={"name": payload, "start_url": "https://example.org/"})
    assert res.status_code == 200 or res.status_code == 303
    listing = client.get("/projects").text
    assert payload not in listing
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in listing


def test_cross_origin_post_rejected(client: TestClient) -> None:
    res = client.post(
        "/projects/new",
        data={"name": "Evil", "start_url": "https://example.com/"},
        headers={"Origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_untrusted_host_header_rejected(client: TestClient) -> None:
    res = client.get("/", headers={"Host": "attacker.example"})
    assert res.status_code == 400


def test_language_switch_and_open_redirect_guard(client: TestClient) -> None:
    res = client.post("/preferences/language", data={"language": "en", "next": "//evil.example"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/"
    assert "Dashboard" in client.get("/").text or "Welcome" in client.get("/").text


def test_unknown_page_is_friendly_404(client: TestClient) -> None:
    res = client.get("/projects/999999")
    assert res.status_code == 404
    assert "bulunamadı" in res.text
