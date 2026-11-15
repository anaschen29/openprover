"""Offline hosted-tool tests: no credentials, real computation, or paid requests."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from openprover import cli
from openprover.budget import ResearchBudget
from openprover.llm.openai import OpenAIClient
from openprover.llm import hosted_tools
from openprover.research import ResearchProver
from openprover.tui import HeadlessTUI


def response(text="Conditional result", *, code=True, status="completed", annotations=()):
    output = []
    if code:
        output.append({"type": "code_interpreter_call", "id": "ci_1", "status": status,
                       "container_id": "cntr_1", "code": "print(1 + 1)",
                       "outputs": [{"type": "logs", "logs": "2"}]})
    if text:
        output.append({"type": "message", "content": [{"type": "output_text", "text": text,
                                                        "annotations": list(annotations)}]})
    return {"id": "resp_test", "status": "completed", "output": output,
            "usage": {"input_tokens": 100, "output_tokens": 20}}


class HostedToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = OpenAIClient(archive_dir=self.root, api_key="fake", python_tools=True)

    def invoke(self, raw, **kwargs):
        with patch.object(self.client, "_request", return_value=copy.deepcopy(raw)) as request:
            result = self.client.call("test", "system", **kwargs)
        return result, request.call_args.args[0]

    def test_python_opt_in_and_defaults_unchanged(self):
        default = OpenAIClient(api_key="fake")
        self.assertNotIn("tools", default._payload([]))
        payload = self.client._payload([])
        self.assertEqual(payload["tools"], [{"type": "code_interpreter", "container": {"type": "auto"}}])
        self.assertIn("code_interpreter_call.outputs", payload["include"])
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["reasoning"], {"mode": "pro", "effort": "max", "summary": "auto"})

    def test_python_and_existing_lean_function_tools_can_coexist(self):
        tool = {"type": "function", "function": {"name": "lean_verify", "parameters": {}}}
        payload = self.client._payload([], tools=[tool])
        self.assertEqual([t["type"] for t in payload["tools"]], ["function", "code_interpreter"])

    def test_literature_search_is_explicit_and_excludes_python(self):
        _, payload = self.invoke(response(code=False), web_search=True)
        self.assertEqual(payload["tools"], [{"type": "web_search"}])
        self.assertEqual(payload["tool_choice"], {"type": "web_search"})
        self.assertIn("web_search_call.action.sources", payload["include"])
        self.assertNotIn("code_interpreter_call.outputs", payload["include"])

    def test_complete_code_and_outputs_archived_and_visible_to_next_agent(self):
        result, _ = self.invoke(response())
        directory = self.root / "call_001.tools"
        self.assertEqual((directory / "code_001.py").read_text(), "print(1 + 1)")
        manifest = json.loads((directory / "manifest.json").read_text())
        self.assertEqual(manifest["calls"][0]["outputs"][0]["logs"], "2")
        self.assertIn("print(1 + 1)", result["result"])
        self.assertIn('"logs": "2"', result["result"])
        self.assertEqual(result["raw"]["usage"]["output_tokens"], 20)
        self.assertEqual(result["tool_calls"], [])  # Never dispatch built-ins as Lean functions.

    def test_web_citations_and_consulted_sources_are_preserved(self):
        citation = {"type": "url_citation", "url": "https://example.org/paper", "title": "Paper",
                    "start_index": 0, "end_index": 8}
        raw = response(code=False, annotations=[citation])
        raw["output"].insert(0, {"type": "web_search_call", "id": "ws_1", "status": "completed",
            "action": {"type": "search", "queries": ["convex bandit"],
                       "sources": [{"type": "url", "url": "https://example.org/other"}]}})
        result, _ = self.invoke(raw, web_search=True)
        manifest = json.loads((self.root / "call_001.tools/manifest.json").read_text())
        self.assertEqual(manifest["citations"], [citation])
        self.assertIn("https://example.org/other", result["result"])
        self.assertIn("https://example.org/paper", result["result"])

    def test_failed_and_not_run_are_not_reported_as_passed(self):
        result, _ = self.invoke(response(status="failed"))
        self.assertIn("ci_1: failed", result["result"])
        result, _ = self.invoke(response(code=False))
        self.assertIn("NOT RUN", result["result"])

    def test_tool_only_response_does_not_become_proof_or_reasoning_summary(self):
        raw = response(text="")
        raw["output"].append({"type": "reasoning", "summary": [{"text": "Possible solution"}]})
        result, _ = self.invoke(raw)
        self.assertEqual(result["result"], "")
        self.assertEqual(result["thinking"], "")
        self.assertTrue((self.root / "call_001.tools/code_001.py").exists())

    def test_truncated_evidence_keeps_full_disk_copy_and_verdict_last(self):
        raw = response("VERDICT: INCONCLUSIVE - gap remains")
        raw["output"][0]["outputs"][0]["logs"] = "x" * 30000
        result, _ = self.invoke(raw)
        self.assertIn("excerpt truncated", result["result"])
        self.assertTrue(result["result"].endswith("VERDICT: INCONCLUSIVE - gap remains"))
        self.assertGreater(len((self.root / "call_001.tools/evidence.md").read_text()), 30000)

    def test_file_download_uses_ids_safe_filename_and_deduplication(self):
        citation = {"type": "container_file_citation", "container_id": "cntr_1", "file_id": "cfile_1",
                    "filename": "../../outside.txt"}
        with patch.object(hosted_tools, "download_file", return_value=b"evidence") as download:
            self.invoke(response(annotations=[citation, citation]))
        download.assert_called_once_with("https://api.openai.com/v1", "fake", "cntr_1", "cfile_1")
        manifest = json.loads((self.root / "call_001.tools/manifest.json").read_text())
        saved = Path(manifest["files"][0]["local_path"])
        self.assertEqual(saved.parent, self.root / "call_001.tools")
        self.assertEqual(saved.read_bytes(), b"evidence")
        self.assertIn("sha256", manifest["files"][0])

    def test_expired_file_preserves_response_and_usage(self):
        citation = {"type": "container_file_citation", "container_id": "cntr_1", "file_id": "cfile_1",
                    "filename": "data.csv"}
        with patch.object(hosted_tools, "download_file", side_effect=RuntimeError("expired")):
            result, _ = self.invoke(response(annotations=[citation]))
        self.assertIn("DOWNLOAD FAILED", result["result"])
        self.assertEqual(result["raw"]["usage"]["output_tokens"], 20)
        self.assertTrue((self.root / "call_001.raw.json").exists())

    def test_download_rejects_paths_redirects_and_oversized_files(self):
        with self.assertRaises(ValueError):
            hosted_tools.download_file("https://api.openai.com/v1", "fake", "../secret", "file")
        with self.assertRaises(RuntimeError):
            hosted_tools._NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere")
        stream = io.BytesIO(b"x" * (hosted_tools.MAX_FILE_BYTES + 1))
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value = stream
            with self.assertRaisesRegex(ValueError, "10 MiB"):
                hosted_tools.download_file("https://api.openai.com/v1", "fake", "cntr_1", "cfile_1")

    def test_unsupported_tool_error_does_not_fallback(self):
        error = urllib.error.HTTPError("https://api.openai.com", 400, "bad request", {},
                                      io.BytesIO(b'{"error":"unsupported tool"}'))
        with patch("urllib.request.urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(RuntimeError, "no model/tool fallback"):
                self.client.call("test", "system")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.client.model, "gpt-6-astra")

    def test_stream_and_nonstream_save_identical_evidence(self):
        raw = response()
        events = [{"type": "response.output_text.delta", "delta": "Conditional result"},
                  {"type": "response.completed", "response": raw}]
        body = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
        seen = []
        with patch("urllib.request.urlopen", return_value=io.BytesIO(body.encode())):
            streamed = self.client.call("test", "system", stream_callback=lambda t,k: seen.append((t,k)))
        ordinary, _ = self.invoke(raw)
        self.assertIn(("Conditional result", "text"), seen)
        self.assertEqual(streamed["raw"], ordinary["raw"])
        self.assertEqual(json.loads((self.root / "call_001.tools/manifest.json").read_text()),
                         json.loads((self.root / "call_002.tools/manifest.json").read_text()))

    def test_fresh_requests_do_not_share_containers(self):
        with patch.object(self.client, "_request", return_value=response()) as request:
            self.client.call("worker", "system")
            self.client.call("review", "system")
        for call in request.call_args_list:
            payload = call.args[0]
            self.assertNotIn("previous_response_id", payload)
            self.assertFalse(any(i.get("type") == "code_interpreter_call" for i in payload["input"]))
            self.assertEqual(payload["tools"][0]["container"], {"type": "auto"})

    def test_function_continuation_replays_hosted_context(self):
        raw = response()
        raw["output"].append({"type": "function_call", "call_id": "fc1", "name": "lean_verify", "arguments": "{}"})
        result, _ = self.invoke(raw)
        items = self.client._input([{"role": "assistant", "tool_calls": result["tool_calls"]},
                                   {"role": "tool", "tool_call_id": "fc1", "content": "OK"}])
        self.assertEqual(items[0]["type"], "code_interpreter_call")
        self.assertEqual(items[-1]["type"], "function_call_output")

    def test_researcher_and_reviewer_receive_executable_tools_and_evidence(self):
        prover = ResearchProver(work_dir=self.root, theorem_text="Fixed target", mode="research",
            budget=ResearchBudget(self.root, "tokens", 200), make_llm=lambda _: self.client,
            make_worker_llm=lambda _: self.client, model_name="offline", autonomous=True,
            verbose=False, tui=HeadlessTUI(), isolation=True)
        with patch.object(self.client, "_request", side_effect=[response(), response("VERDICT: INCONCLUSIVE")]) as req:
            with contextlib.redirect_stdout(io.StringIO()):
                worker = prover._run_worker({"description": "Check edge cases"}, "worker_1", self.root / "w.md")
                reviewer = prover._run_verifier("Check edge cases", worker["result"], "verifier_1", self.root / "v.md")
        inputs = req.call_args_list
        self.assertIn("Hosted Code Interpreter", inputs[0].args[0]["input"][0]["content"])
        self.assertNotIn("no execution tools", inputs[1].args[0]["input"][0]["content"])
        self.assertIn("print(1 + 1)", inputs[1].args[0]["input"][1]["content"])
        self.assertTrue(reviewer["result"].endswith("VERDICT: INCONCLUSIVE"))

    def test_cli_routes_search_on_worker_and_persists_python(self):
        objective = self.root / "objective.md"
        objective.write_text("Improve a bound")
        run = self.root / "run"
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake"}), patch.object(cli, "ResearchProver") as cls:
            instance = cls.return_value
            def run_fake():
                args = cls.call_args.kwargs
                instance.budget = args["budget"]
                instance.work_dir = args["work_dir"]
                instance.mode = "research"
                planner = args["make_llm"](run)
                worker = args["make_worker_llm"](run)
                self.assertFalse(planner.python_tools)
                self.assertTrue(worker.python_tools)
                self.assertFalse(args["isolation"])
                instance.planner_llm, instance.worker_llm = planner, worker
            instance.run.side_effect = run_fake
            with patch("sys.argv", ["openprover", str(run), "--mode", "research", "--theorem", str(objective),
                                   "--python", "--no-isolation", "--headless"]), contextlib.redirect_stdout(io.StringIO()):
                cli.main()
        self.assertTrue(cli._load_run_config(run)["python_tools"])
        self.assertFalse(cli._load_run_config(run)["isolation"])

    def test_cli_rejects_python_for_unsupported_provider_or_legacy_mode(self):
        objective = self.root / "objective.md"
        objective.write_text("Claim")
        for flags in (["--model", "sonnet", "--mode", "research"], []):
            with self.subTest(flags=flags), patch("sys.argv", ["openprover", str(objective), "--python", *flags]), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                cli.main()
            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
