"""Archive Responses hosted-tool evidence without executing returned code locally."""
import hashlib
import json
import re
import urllib.request
from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 16
MAX_CONTEXT_CHARS = 24000


def configure_tools(payload, *, python=False, web_search=False):
    """Built-ins execute server-side, not through OpenProver's Lean dispatcher."""
    if python:
        payload.setdefault("tools", []).append({
            "type": "code_interpreter", "container": {"type": "auto"}})
        payload["include"].append("code_interpreter_call.outputs")
    if web_search:
        payload.setdefault("tools", []).append({"type": "web_search"})
        payload["include"].append("web_search_call.action.sources")
        # A literature_search assignment must actually search, not rely on recall.
        payload["tool_choice"] = {"type": "web_search"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Refusing redirect for authenticated artifact download")


def download_file(base_url, api_key, container_id, file_id):
    """Download only from the configured API, never a model-supplied URL."""
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", value or "")
               for value in (container_id, file_id)):
        raise ValueError("Invalid container/file ID")
    endpoint = f"{base_url}/containers/{container_id}/files/{file_id}/content"
    request = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
        data = response.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Artifact exceeds 10 MiB download limit")
    return data


def archive_tools(raw, payload, call_path, *, base_url, api_key):
    """Preserve complete returned evidence; pass a bounded excerpt to the planner.

    An execution item with status 'completed' is not a passing mathematical test.
    Citations are sources supplied by the API, not independently verified theorems.
    """
    requested = {tool["type"] for tool in payload.get("tools", [])}
    if not requested.intersection({"code_interpreter", "web_search"}):
        return ""
    directory = Path(call_path).with_suffix(".tools")
    directory.mkdir(parents=True, exist_ok=True)
    calls, citations, files = [], [], []
    for item in raw.get("output", []):
        if item.get("type") in ("code_interpreter_call", "web_search_call"):
            calls.append(item)
        if item.get("type") == "message":
            for part in item.get("content", []):
                for annotation in part.get("annotations", []):
                    if annotation.get("type") == "url_citation":
                        citations.append(annotation)
                    elif annotation.get("type") == "container_file_citation":
                        files.append(annotation)

    manifest = {"response_id": raw.get("id"), "response_status": raw.get("status"),
                "requested_tools": sorted(requested), "calls": calls,
                "citations": citations, "files": []}
    parts = ["# Hosted-tool evidence (API records, not a proof certificate)"]
    for kind in ("code_interpreter", "web_search"):
        matching = [c for c in calls if c["type"] == kind + "_call"]
        if kind in requested and not matching:
            parts.append(f"{kind}: NOT RUN (no execution record returned).")
    for number, item in enumerate(calls, 1):
        parts.append(f"## {item['type']} {item.get('id', '')}: {item.get('status', 'unknown')}")
        if item["type"] == "code_interpreter_call":
            code = item.get("code")
            if isinstance(code, str):
                (directory / f"code_{number:03d}.py").write_text(code, encoding="utf-8")
                parts.append("```python\n" + code + "\n```")
            parts.append("Returned outputs:\n" + json.dumps(item.get("outputs"), ensure_ascii=False))
        else:
            parts.append("Search/open action and returned sources:\n" +
                         json.dumps(item.get("action"), ensure_ascii=False))
    if citations:
        parts.append("## Citation annotations\n" + json.dumps(citations, ensure_ascii=False))
    seen = set()
    for annotation in files:
        key = (annotation.get("container_id"), annotation.get("file_id"))
        if key in seen:
            continue
        seen.add(key)
        entry = dict(annotation)
        manifest["files"].append(entry)
        if len(seen) > MAX_FILES:
            entry.update(status="NOT DOWNLOADED", error="Per-response file limit reached")
            continue
        filename = re.sub(r"[^A-Za-z0-9._-]", "_",
                          str(annotation.get("filename", "artifact")))[-120:]
        filename = f"file_{len(seen):03d}_{filename}"
        try:
            data = download_file(base_url, api_key, *key)
            target = directory / filename
            target.write_bytes(data)
            entry.update(status="saved", local_path=str(target), size=len(data),
                         sha256=hashlib.sha256(data).hexdigest())
        except (OSError, ValueError, RuntimeError) as exc:
            # Preserve the response and token usage even if ephemeral files expired.
            entry.update(status="DOWNLOAD FAILED", error=type(exc).__name__)
    if manifest["files"]:
        parts.append("## Generated files\n" + json.dumps(manifest["files"], ensure_ascii=False))
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = "\n\n".join(parts)
    (directory / "evidence.md").write_text(evidence, encoding="utf-8")
    if len(evidence) > MAX_CONTEXT_CHARS:
        evidence = evidence[:MAX_CONTEXT_CHARS] + "\n[Evidence excerpt truncated; do not assume omitted checks passed.]"
    return evidence + f"\n\nFull evidence: {directory / 'evidence.md'}; manifest: {path}"
