from app.utils import auth_utils


class _Response:
    status_code = 200

    def json(self):
        return {"success": True}


class _Session:
    def __init__(self, seen):
        self.trust_env = True
        self._seen = seen

    def request(self, method, url, **kwargs):
        self._seen.update(
            method=method,
            url=url,
            trust_env=self.trust_env,
            kwargs=kwargs,
        )
        return _Response()


def test_request_django_disables_environment_proxy(monkeypatch):
    seen = {}
    monkeypatch.setattr(auth_utils.requests, "Session", lambda: _Session(seen))

    response = auth_utils.request_django(
        "GET", "http://127.0.0.1:8001/user/detail/", "token"
    )

    assert response.status_code == 200
    assert seen["trust_env"] is False
    assert seen["kwargs"]["headers"]["Authorization"] == "Bearer token"
