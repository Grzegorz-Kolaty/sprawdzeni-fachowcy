import httpx
from pytest import MonkeyPatch

from app.providers.website_page_inspector import WebsitePageInspection, WebsitePageInspector


def _inspect_html_response(
    monkeypatch: MonkeyPatch,
    *,
    body: bytes,
    content_type: str,
) -> WebsitePageInspection:
    url = "https://example.test/"
    response = httpx.Response(
        200,
        headers={
            "content-type": content_type,
        },
        content=body,
        request=httpx.Request(
            "GET",
            url,
        ),
    )

    monkeypatch.setattr(
        WebsitePageInspector,
        "_ensure_safe_url",
        lambda self, url: None,
    )
    monkeypatch.setattr(
        WebsitePageInspector,
        "_get_with_safe_redirects",
        lambda self, client, url, same_site_hostname: response,
    )

    return WebsitePageInspector().inspect(url)


def test_decodes_utf8_html_from_meta_when_http_charset_is_wrong(
    monkeypatch: MonkeyPatch,
) -> None:
    html = """
    <html>
      <head>
        <meta charset="utf-8">
        <title>Montaż klimatyzacji</title>
      </head>
      <body>Księżnej Elżbiety, sprzedaż i montaż</body>
    </html>
    """

    inspection = _inspect_html_response(
        monkeypatch,
        body=html.encode("utf-8"),
        content_type="text/html; charset=iso-8859-1",
    )

    assert inspection.title == "Montaż klimatyzacji"
    assert "sprzedaż" in inspection.visible_text
    assert "Księżnej Elżbiety" in inspection.visible_text
    assert "MontaÅ¼" not in inspection.html


def test_decodes_utf8_html_with_deterministic_fallback_when_charset_is_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    html = "<html><body>Zażółć gęślą jaźń</body></html>"

    inspection = _inspect_html_response(
        monkeypatch,
        body=html.encode("utf-8"),
        content_type="text/html",
    )

    assert "Zażółć gęślą jaźń" in inspection.visible_text
