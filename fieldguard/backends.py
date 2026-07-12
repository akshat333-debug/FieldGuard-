"""LLM backends: protocol, offline mock, OpenAI-compatible client."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class Backend(Protocol):
    calls: int

    def generate(self, prompt: str, *, force_json: bool = False) -> str: ...


def _document_block(prompt: str) -> str:
    """Text between 'DOCUMENT:' and the next all-caps section marker (or end)."""
    m = re.search(r"DOCUMENT:\n(.*?)(?:\n[A-Z][A-Z ]+:\n|\Z)", prompt, re.S)
    return m.group(1) if m else ""


def _fields_requested(prompt: str) -> list[str]:
    """Field names listed after 'FIELDS:' as '- name (type)' lines."""
    return re.findall(r"^- (\w+) \(", prompt, re.M)


class MockBackend:
    """Offline backend for tests/demo.

    Acts as a perfect extractor over synthetic documents whose bodies contain
    ``field: value`` lines — then applies ``corruptions`` (field -> wrong value)
    ONLY when ``force_json=True``. This simulates constraint-induced value
    corruption with exact, controllable ground truth.
    """

    def __init__(self, corruptions: dict[str, str] | None = None):
        self.corruptions = corruptions or {}
        self.calls = 0

    def _read_values(self, doc: str) -> dict[str, str]:
        vals: dict[str, str] = {}
        for line in doc.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                vals[k.strip().casefold()] = v.strip()
        return vals

    def generate(self, prompt: str, *, force_json: bool = False) -> str:
        self.calls += 1
        doc_vals = self._read_values(_document_block(prompt))
        wanted = _fields_requested(prompt)

        if not wanted:  # single-field verification query: "FIELD: <name>"
            m = re.search(r"^FIELD: (\w+)$", prompt, re.M)
            name = m.group(1) if m else ""
            return doc_vals.get(name.casefold(), "unknown")

        answers = {n: doc_vals.get(n.casefold(), "unknown") for n in wanted}
        if force_json:
            answers = {n: self.corruptions.get(n, v) for n, v in answers.items()}
            return json.dumps(answers)
        return "\n".join(f"{n}: {v}" for n, v in answers.items())


class OpenAICompatBackend:
    """Minimal client for any /v1/chat/completions endpoint (OpenAI, Ollama, vLLM).

    # ponytail: sync urllib, no retries/streaming; add a real client lib only if
    # rate limits or streaming become a need.
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 512,
                 timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.temperature = temperature
        self.max_tokens = max_tokens  # unbounded free-form output can run past
        self.timeout = timeout        # any timeout on small local models
        self.calls = 0

    def generate(self, prompt: str, *, force_json: bool = False) -> str:
        self.calls += 1
        body: dict = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if force_json:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        for attempt in (1, 2):  # one retry on timeout
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.load(resp)
                return data["choices"][0]["message"]["content"]
            except TimeoutError:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")
