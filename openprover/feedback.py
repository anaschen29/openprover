"""Durable, non-interrupting feedback for a research run; no model calls."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def _write_json(path, value):
    """Publish complete JSON atomically; concurrent senders use distinct files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class FeedbackInbox:
    """Immutable messages; only the running coordinator writes delivery receipts."""

    def __init__(self, run_dir):
        self.root = Path(run_dir) / "feedback"

    def messages(self):
        messages = []
        for path in sorted((self.root / "messages").glob("*.json")):
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("id") != path.stem or not isinstance(item.get("message"), str):
                raise ValueError(f"Invalid feedback message: {path}")
            messages.append(item)
        return messages

    def active(self):
        messages = self.messages()
        superseded = {m.get("supersedes") for m in messages}
        return [m for m in messages if m["id"] not in superseded]

    def send(self, message, supersedes=None):
        message = message.strip()
        if not message or len(message) > 16000:
            raise ValueError("Feedback must contain 1 to 16000 characters")
        if supersedes and supersedes not in {m["id"] for m in self.messages()}:
            raise ValueError(f"Unknown feedback ID: {supersedes}")
        identifier = f"F-{time.time_ns()}-{uuid.uuid4().hex[:8]}"
        item = {"id": identifier, "message": message, "supersedes": supersedes}
        _write_json(self.root / "messages" / f"{identifier}.json", item)
        return identifier

    def receipts(self):
        path = self.root / "receipts.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def record(self, identifiers, event, step):
        if not identifiers:
            return
        if event not in ("delivered", "acknowledged"):
            raise ValueError(f"Invalid feedback event: {event}")
        receipts = self.receipts()
        for identifier in identifiers:
            # First delivery/accepted planning step is enough; avoid duplicate events.
            receipts.setdefault(identifier, {}).setdefault(event, step)
        _write_json(self.root / "receipts.json", receipts)

    def acknowledged_ids(self):
        receipts = self.receipts()
        return tuple(m["id"] for m in self.active()
                     if "acknowledged" in receipts.get(m["id"], {}))

    @staticmethod
    def render(messages):
        if not messages:
            return ""
        return (
            "# Active human research guidance\n"
            "Acknowledge each new ID and your response in the whiteboard. Apply this "
            "guidance to research priorities; do not treat suggestions as proved lemmas, "
            "silently change the fixed objective, or extend resource limits. "
            "If guidance conflicts with the objective, record the conflict explicitly. "
            "Later messages supersede earlier ones only where explicitly stated.\n\n"
            + "\n\n".join(f"## {m['id']}\n{m['message']}" for m in messages)
        )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="openprover feedback",
                                     description="Queue guidance without interrupting research")
    parser.add_argument("run_dir", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--message")
    source.add_argument("--file", type=Path)
    source.add_argument("--list", action="store_true")
    parser.add_argument("--supersedes", metavar="ID", help="Replace an earlier guidance message")
    args = parser.parse_args(argv)
    if not (args.run_dir / "research_state.json").is_file():
        parser.error("run_dir must be an existing research run")
    if args.list and args.supersedes:
        parser.error("--supersedes requires --message or --file")
    inbox = FeedbackInbox(args.run_dir)
    try:
        if args.list:
            active = {m["id"] for m in inbox.active()}
            receipts = inbox.receipts()
            for item in inbox.messages():
                receipt = receipts.get(item["id"], {})
                status = ("superseded" if item["id"] not in active else
                          "acknowledged" if "acknowledged" in receipt else
                          "delivered" if "delivered" in receipt else "queued")
                print(f"{item['id']} [{status}] {item['message']}")
        else:
            text = args.file.read_text(encoding="utf-8") if args.file else args.message
            identifier = inbox.send(text, args.supersedes)
            print(f"Queued {identifier}. Active work is not interrupted; "
                  "a finished run still requires explicit continuation.")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
