from backend.app.main import app
from backend.app.observability.sanitizer import sanitize, sanitize_error


def test_sanitize_redacts_secret_keys_and_cookie_values() -> None:
    value = {
        "Authorization": "Bearer eyJabc.def.ghi",
        "nested": {"accessToken": "eyJsecret.secret.secret", "safe": "hello"},
        "header": "session=abcdefghijklmnopqrstuvwxyz; theme=light",
    }

    sanitized = sanitize(value)

    assert sanitized["Authorization"] == "<redacted>"
    assert sanitized["nested"]["accessToken"] == "<redacted>"
    assert sanitized["nested"]["safe"] == "hello"
    assert "abcdefghijklmnopqrstuvwxyz" not in sanitized["header"]


def test_sanitize_error_redacts_jwt_like_values() -> None:
    error = RuntimeError(
        "Authorization: Bearer eyJaaaaaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbb.cccccccccc"
    )

    assert "eyJaaaaaaaa" not in sanitize_error(error)


def test_local_api_does_not_expose_video_routes() -> None:
    paths = {str(getattr(route, "path", "")) for route in app.routes}

    assert not any("/video" in path.lower() for path in paths)
