"""Small provider-neutral HTTP client for read-only dashboard analysis."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PROVIDERS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openai_compatible": "OpenAI-compatible",
}

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5-mini",
    "anthropic": "claude-sonnet-4-5",
    "openai_compatible": "",
}

SYSTEM_PROMPT = """You are a careful, read-only endurance training analyst embedded in a personal dashboard.
Use only the structured dashboard context supplied by the application. Never invent absent metrics.
Prioritize moving time and moving pace when evaluating performance, while explaining elapsed and stopped time separately.
Use the complete heart-rate-zone distribution when HR exists. Treat missing HR, GPS, altitude, or sparse sampling as uncertainty.
Clearly separate measured facts from interpretations. Compare the selected activity or period with the supplied recent history and trends where useful.
Do not diagnose illness or give medical treatment. Flag potentially concerning signals as reasons to rest or consult a qualified professional.
Write an actionable summary with: performance, pacing, heart rate and zones, comparison with baseline, data limitations, and practical next steps.
Mention concrete values and dates from the supplied context."""


class AIProviderError(RuntimeError):
    pass


def _request_json(method, url, headers, payload=None, timeout=60):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise AIProviderError(f"Provider returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise AIProviderError(f"Could not reach the AI provider: {error.reason}") from error
    except (json.JSONDecodeError, TimeoutError) as error:
        raise AIProviderError(f"Invalid or timed-out provider response: {error}") from error


def _base_url(provider, custom_base_url=""):
    custom = str(custom_base_url).strip().rstrip("/")
    if provider == "openai_compatible":
        if not custom:
            raise AIProviderError("An API base URL is required for an OpenAI-compatible provider.")
        parsed = urlparse(custom)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AIProviderError("The custom API base URL is not valid.")
        if parsed.scheme != "https" and parsed.hostname not in local_hosts:
            raise AIProviderError("Remote custom providers must use HTTPS. HTTP is allowed only for a local provider.")
        return custom
    return {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
    }.get(provider, "")


def list_models(provider, api_key, custom_base_url=""):
    if provider == "gemini":
        result = _request_json("GET", "https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": api_key})
        return sorted(item["name"].removeprefix("models/") for item in result.get("models", []) if "generateContent" in item.get("supportedGenerationMethods", []))
    base = _base_url(provider, custom_base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    if provider == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    result = _request_json("GET", f"{base}/models", headers)
    return sorted(str(item.get("id")) for item in result.get("data", []) if item.get("id"))


def generate_analysis(provider, api_key, model, dashboard_context, additional_instructions="", custom_base_url="", max_output_tokens=1800, follow_up=None, previous_answer=None):
    context_json = json.dumps(dashboard_context, ensure_ascii=False, separators=(",", ":"))
    request_text = "Analyze the activity or period currently open in the dashboard from this context:\n" + context_json
    if additional_instructions.strip():
        request_text += "\n\nUser preferences:\n" + additional_instructions.strip()
    if follow_up:
        request_text += "\n\nFollow-up question:\n" + follow_up.strip()
        if previous_answer:
            request_text += "\n\nPrevious analysis for continuity:\n" + previous_answer

    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": request_text}]}],
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": int(max_output_tokens)},
        }
        result = _request_json("POST", url, {"x-goog-api-key": api_key, "Content-Type": "application/json"}, payload)
        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts).strip()
    elif provider == "anthropic":
        base = _base_url(provider, custom_base_url)
        payload = {"model": model, "max_tokens": int(max_output_tokens), "temperature": 0.25, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": request_text}]}
        result = _request_json("POST", f"{base}/messages", {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, payload)
        text = "\n".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text").strip()
    elif provider == "openai":
        base = _base_url(provider, custom_base_url)
        payload = {"model": model, "instructions": SYSTEM_PROMPT, "input": request_text, "max_output_tokens": int(max_output_tokens)}
        result = _request_json("POST", f"{base}/responses", {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, payload)
        text = str(result.get("output_text", "")).strip()
        if not text:
            text = "\n".join(content.get("text", "") for output in result.get("output", []) for content in output.get("content", []) if content.get("type") == "output_text").strip()
    else:
        base = _base_url(provider, custom_base_url)
        payload = {"model": model, "temperature": 0.25, "max_tokens": int(max_output_tokens), "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": request_text}]}
        result = _request_json("POST", f"{base}/chat/completions", {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, payload)
        text = str(result.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
    if not text:
        raise AIProviderError("The provider returned no text analysis.")
    return text
