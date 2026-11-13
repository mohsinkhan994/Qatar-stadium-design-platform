import httpx
from .base import ProviderError


class CloudProvider:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def post(self, url, headers, body):
        try:
            with httpx.Client(timeout=httpx.Timeout(self.settings.timeout, connect=15), transport=self.transport,
                              follow_redirects=False) as client:
                response = client.post(url, headers=headers, json=body)
            if response.status_code in (401, 403):
                raise ProviderError("provider_access", "Provider authentication or model access failed. Check server configuration.")
            if response.status_code == 429:
                raise ProviderError("provider_limit", "Provider rate limit or billing quota reached. Try later after checking the account.")
            if response.status_code >= 400:
                raise ProviderError("provider_rejected", f"Provider rejected the request (HTTP {response.status_code}). Check model settings or try different choices.")
            return response.json(), response.headers.get("x-request-id")
        except httpx.TimeoutException as exc:
            raise ProviderError("provider_timeout", "Provider timed out. No automatic retry was made; the request may have been billed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable", "Could not reach the image provider. Check connectivity.") from exc
        except ValueError as exc:
            raise ProviderError("provider_response", "Provider returned an unreadable response.") from exc
