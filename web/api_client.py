"""Le client de l'API de calcul (voir docs/api.md).

C'est la SEULE partie du site qui connaît le serveur de calcul : tout le reste (pages, cartes)
ne manipule que ce que renvoient ces méthodes. Changer l'affichage ne touche donc pas ici.
"""

import requests


class Unreachable(Exception):
    """Le serveur de calcul ne répond pas (éteint, mauvaise adresse, trop lent)."""


class ApiError(Exception):
    """Réponse d'erreur de l'API : `{"error": "...", "code": "..."}` + le code HTTP."""

    def __init__(self, status: int, code: str, message: str, body: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.body = status, code, message, body or {}


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # -- transport (les tests le remplacent pour parler au serveur sans réseau)
    def _request(self, method: str, path: str, **kwargs) -> tuple[int, object]:
        try:
            r = requests.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise Unreachable(f"Serveur de calcul injoignable ({self.base_url})") from exc
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"error": "Réponse inattendue du serveur de calcul", "code": "bad_response"}

    def _call(self, method: str, path: str, **kwargs):
        status, body = self._request(method, path, **kwargs)
        if status >= 400:
            body = body if isinstance(body, dict) else {}
            raise ApiError(status, body.get("code", "error"), body.get("error", f"Erreur {status}"), body)
        return body

    # -- les routes de docs/api.md
    def health(self) -> dict:
        return self._call("GET", "/api/health")

    def solvers(self) -> list[dict]:
        return self._call("GET", "/api/solvers")

    def instances(self) -> list[dict]:
        return self._call("GET", "/api/instances")

    def instance(self, instance_id: str) -> dict:
        return self._call("GET", f"/api/instances/{instance_id}")

    def upload(self, data: bytes, filename: str) -> dict:
        return self._call("POST", "/api/instances", files={"file": (filename, data)})

    def start_job(self, instance_id: str, solver: str, time_limit: float, seed: int) -> dict:
        return self._call("POST", "/api/jobs", json={
            "instance_id": instance_id, "solver": solver, "time_limit": time_limit, "seed": seed})

    def job(self, job_id: str) -> dict:
        return self._call("GET", f"/api/jobs/{job_id}")

    def stop(self, job_id: str) -> dict:
        return self._call("POST", f"/api/jobs/{job_id}/stop")
