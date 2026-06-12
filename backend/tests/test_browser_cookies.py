from pathlib import Path

import pytest

from backend.app.auth.browser_cookies import BrowserCookieProvider, CookieAccessError
from backend.app.config.settings import Settings


def test_manual_cookie_parser(tmp_path: Path) -> None:
    provider = BrowserCookieProvider(Settings(qm_data_dir=tmp_path))

    cookies = provider.from_manual_header(
        "session=abc; accessToken=token", "https://bbvamx.quantummetric.com"
    )

    assert [cookie.name for cookie in cookies] == ["session", "accessToken"]
    assert provider.cookie_header(cookies, "https://bbvamx.quantummetric.com/data/init") == (
        "session=abc; accessToken=token"
    )


def test_manual_cookie_parser_rejects_empty(tmp_path: Path) -> None:
    provider = BrowserCookieProvider(Settings(qm_data_dir=tmp_path))

    with pytest.raises(CookieAccessError):
        provider.from_manual_header("invalid", "https://bbvamx.quantummetric.com")
