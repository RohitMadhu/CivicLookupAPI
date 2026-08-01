def test_docs_page_at_root():
    from app import app as full_app

    client = full_app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "CivicLookup" in body
    assert "/v1/lookup/zip/60601" in body
    assert "/api/rep/60601" in body
    assert "/v1/lookup/address" in body
    assert "/health" in body
