import asyncio
import base64
import json
import time
from urllib.parse import urlparse

import aiohttp

from app.contracts import Decision


DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "observation": {"type": "string", "enum": ["open", "closed", "uncertain"]},
        "action": {"type": "string", "enum": ["continue", "recheck", "hold", "finish"]},
        "target_view": {"type": ["string", "null"]},
        "reason": {"type": "string", "maxLength": 300},
    },
    "required": ["observation", "action", "target_view", "reason"],
    "additionalProperties": False,
}


class LlamaBackend:
    """Loopback image chat client. Timeouts quarantine this client.

    Closing HTTP does not prove server-side cancellation. After timeout/cancel,
    restart the owned llama-server and create a new client before further inference.
    """
    identity = "llama-server/Qwen3-VL-2B-Instruct"

    def __init__(self, endpoint="http://127.0.0.1:8081", timeout=6):
        url = urlparse(endpoint)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1", "localhost")
                or url.username or url.password or url.query or url.fragment):
            raise ValueError("inference endpoint must be an unauthenticated loopback HTTP URL")
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.busy = False
        self.quarantined = False
        self.session = None

    async def _session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout), trust_env=False)
        return self.session

    async def health(self):
        session = await self._session()
        async with session.get(self.endpoint + "/health", allow_redirects=False) as response:
            if response.status != 200:
                raise RuntimeError(f"llama-server health returned {response.status}")

    async def infer(self, observation):
        prompt = (
            "Inspect the visible gate. Classify open, closed or uncertain. "
            "Return only the specified JSON object. Use recheck for unclear images "
            "only if an alternative view is allowed; otherwise continue or finish. "
            f"Allowed actions: {list(observation.allowed_actions)}. "
            f"Alternative views: {list(observation.allowed_views)}. "
            "target_view must be null except for recheck. Keep reason brief."
        )
        return await self.image(observation.frame.jpeg, prompt, DECISION_SCHEMA, observation.deadline)

    async def image(self, jpeg, prompt, schema, deadline):
        if self.busy or self.quarantined:
            raise RuntimeError("inference busy/quarantined; restart the owned server after timeout")
        self.busy = True
        try:
            session = await self._session()
            body = {
                "model": "local",
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/jpeg;base64," +
                        base64.b64encode(jpeg).decode()
                    }},
                ]}],
                "max_tokens": 128, "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "inspection", "strict": True, "schema": schema}},
            }
            remaining = min(self.timeout, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("request expired before dispatch")
            async with asyncio.timeout(remaining):
                async with session.post(self.endpoint + "/v1/chat/completions",
                                        json=body, allow_redirects=False) as response:
                    response.raise_for_status()
                    if response.status != 200:
                        raise RuntimeError("unexpected inference HTTP status")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(8192):
                        data.extend(chunk)
                        if len(data) > 65536:
                            raise ValueError("oversized inference HTTP response")
                    result = json.loads(data)
                    raw = result["choices"][0]["message"]["content"]
                    if not isinstance(raw, str):
                        raise ValueError("model returned non-text content")
                    return raw
        except (TimeoutError, asyncio.CancelledError, aiohttp.ClientError):
            self.quarantined = True
            raise
        finally:
            self.busy = False

    async def close(self):
        if self.session:
            await self.session.close()


class QwenPolicy:
    def __init__(self, backend):
        self.backend = backend
        self.identity = backend.identity

    async def infer(self, observation):
        return await self.backend.infer(observation)

    async def close(self):
        await self.backend.close()
