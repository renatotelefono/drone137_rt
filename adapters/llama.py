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
                timeout=aiohttp.ClientTimeout(total=self.timeout), trust_env=False,
                # Inspections can be farther apart than the model server's
                # keep-alive timeout. Avoid reusing a closing idle socket for
                # a POST; do not retry uncertain in-flight inference requests.
                connector=aiohttp.TCPConnector(force_close=True))
        return self.session

    async def health(self):
        session = await self._session()
        async with session.get(self.endpoint + "/health", allow_redirects=False) as response:
            if response.status != 200:
                raise RuntimeError(f"llama-server health returned {response.status}")

    async def infer(self, observation):
        from app.perception import PROMPT, SCHEMA, parse
        visual = parse(await self.image(observation.frame.jpeg, PROMPT, SCHEMA, observation.deadline))
        label = {'open_space': 'open', 'solid_surface': 'closed', 'uncertain': 'uncertain'}[visual['center']]
        action, target = 'continue', None
        if label == 'uncertain' and 'recheck' in observation.allowed_actions and observation.allowed_views:
            action, target = 'recheck', observation.allowed_views[0]
        elif action not in observation.allowed_actions:
            action = next((a for a in ('finish', 'hold') if a in observation.allowed_actions), None)
            if action is None:
                raise ValueError('No supported inspection action available')
        return json.dumps({'observation': label, 'action': action, 'target_view': target,
                           'reason': visual['visible_evidence']})

    async def image(self, jpeg, prompt, schema, deadline, reference=None, max_tokens=128):
        content = []
        for data in ([reference, jpeg] if reference is not None else [jpeg]):
            if len(data) > 200_000:
                raise ValueError('Image exceeds size limit')
            content.append({'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,'+base64.b64encode(data).decode()}})
        content.append({'type': 'text', 'text': prompt})
        return await self._complete(content, schema, deadline, max_tokens=max_tokens)

    async def text(self, prompt, schema, deadline):
        return await self._complete([{'type': 'text', 'text': prompt}], schema, deadline)

    async def _complete(self, content, schema, deadline, max_tokens=128):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 384:
            raise ValueError('Output budget must be from 1 through 384 tokens')
        if self.busy or self.quarantined:
            raise RuntimeError("inference busy/quarantined; restart the owned server after timeout")
        self.busy = True
        try:
            session = await self._session()
            body = {
                "model": "local",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": max_tokens, "temperature": 0, "cache_prompt": False,
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
                    choice = result["choices"][0]
                    if choice.get('finish_reason', 'stop') != 'stop':
                        raise ValueError('Incomplete model response; decision rejected')
                    raw = choice["message"]["content"]
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
