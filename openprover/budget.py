"""Budget tracking for proving sessions (token or time limits)."""

import re
import time


def _fmt_tokens(n: int) -> str:
    """Format token count: 500, 12.3k, 1.2M."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        k = n / 1000
        return f"{k:.1f}k" if k < 100 else f"{k:.0f}k"
    m = n / 1_000_000
    return f"{m:.1f}M" if m < 100 else f"{m:.0f}M"


def _fmt_duration(secs: int) -> str:
    """Format seconds: 45s, 14m, 1h12m."""
    if secs < 60:
        return f"{secs}s"
    m = secs // 60
    s = secs % 60
    if m < 60:
        return f"{m}m{s}s" if s else f"{m}m"
    h = m // 60
    rm = m % 60
    return f"{h}h{rm}m" if rm else f"{h}h"


def parse_duration(s: str) -> int:
    """Parse duration string to seconds.

    Accepts: '30m', '2h', '1h30m', '90s', '1800' (plain seconds).
    """
    s = s.strip()
    # Plain integer → seconds
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', s)
    if not m or not any(m.groups()):
        raise ValueError(f"Invalid duration: {s!r} (expected e.g. '30m', '2h', '1h30m')")
    hours = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(m.group(3) or 0)
    total = hours * 3600 + mins * 60 + secs
    if total <= 0:
        raise ValueError(f"Duration must be positive: {s!r}")
    return total


class Budget:
    """Tracks resource budget (output tokens or wall-clock time)."""

    def __init__(self, mode: str, limit: int,
                 conclude_after: float = 0.99):
        assert mode in ("tokens", "time"), f"Invalid budget mode: {mode}"
        self.mode = mode
        self.limit = limit
        self.conclude_after = conclude_after
        self.total_output_tokens = 0
        self.start_time = time.monotonic()

    def fraction_spent(self) -> float:
        if self.mode == "tokens":
            return self.total_output_tokens / max(self.limit, 1)
        else:
            elapsed = time.monotonic() - self.start_time
            return elapsed / max(self.limit, 1)

    def is_exhausted(self) -> bool:
        return self.fraction_spent() >= 1.0

    def should_conclude(self) -> bool:
        return self.fraction_spent() >= self.conclude_after

    def add_output_tokens(self, n: int):
        self.total_output_tokens += n

    def status_str(self) -> str:
        """Short status for header display."""
        if self.mode == "tokens":
            return f"{_fmt_tokens(self.total_output_tokens)}/{_fmt_tokens(self.limit)} tok"
        else:
            elapsed = int(time.monotonic() - self.start_time)
            return f"{_fmt_duration(elapsed)}/{_fmt_duration(self.limit)}"

    def summary_str(self) -> str:
        """Longer status for prompts."""
        pct = int(self.fraction_spent() * 100)
        if self.mode == "tokens":
            return (f"{_fmt_tokens(self.total_output_tokens)}/{_fmt_tokens(self.limit)} "
                    f"output tokens used ({pct}%)")
        else:
            elapsed = int(time.monotonic() - self.start_time)
            return f"{_fmt_duration(elapsed)}/{_fmt_duration(self.limit)} elapsed ({pct}%)"

    def limit_str(self) -> str:
        """Human-readable limit for run_params display."""
        if self.mode == "tokens":
            return f"{_fmt_tokens(self.limit)} tokens"
        else:
            return _fmt_duration(self.limit)


class ResearchBudget(Budget):
    """One explicitly authorized allocation, persisted independently of reports.

    This retains the existing step-boundary budget semantics, not a hard cap on
    in-flight requests. Full request-level accounting remains a separate change.
    """

    STATE_FILE = "research_state.json"

    @classmethod
    def load_state(cls, work_dir):
        import json
        import math
        from pathlib import Path

        path = Path(work_dir) / cls.STATE_FILE
        if not path.exists():
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            valid = (
                state["version"] == 1
                and state["mode"] in ("time", "tokens")
                and state["status"] in ("running", "paused", "finished")
                and type(state["limit"]) is int and state["limit"] > 0
                and type(state["allocation"]) is int and state["allocation"] > 0
                and type(state["output_tokens"]) is int and state["output_tokens"] >= 0
                and 0.9 <= state["conclude_after"] <= 1
                and math.isfinite(state["started_at"])
            )
            if not valid:
                raise ValueError("invalid fields")
            return state
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid research state in {path}; refusing to reset the budget") from exc

    def __init__(self, work_dir, mode, limit, conclude_after=0.99, *,
                 resume=False, renew=False):
        from pathlib import Path

        self.work_dir = Path(work_dir)
        previous = self.load_state(work_dir)
        if mode not in ("time", "tokens") or type(limit) is not int or limit <= 0:
            raise ValueError("Research budgets must have a positive time or token limit")
        if not 0.9 <= conclude_after <= 1:
            raise ValueError("--conclude-after must be between 0.9 and 1.0")
        if resume and previous is None:
            raise ValueError("Research state is missing; refusing to grant a new budget implicitly")
        if previous and not resume:
            raise ValueError("This directory already has a research allocation; resume it instead")
        if renew and (not resume or previous["status"] != "finished"):
            raise ValueError("--continue requires a finished research allocation")
        if previous and not renew:
            if (mode, limit, conclude_after) != (
                previous["mode"], previous["limit"], previous["conclude_after"]
            ):
                raise ValueError("Cannot change an active allocation; use --continue after it finishes")
            self.state = previous
        else:
            if previous:
                self._write(self.work_dir / "reports" /
                            f"allocation_{previous['allocation']:03d}.json", previous)
            self.state = {
                "version": 1,
                "allocation": previous["allocation"] + 1 if previous else 1,
                "status": "running", "mode": mode, "limit": limit,
                "conclude_after": conclude_after,
                "started_at": time.time(), "output_tokens": 0,
            }
        super().__init__(mode, limit, conclude_after)
        self.total_output_tokens = self.state["output_tokens"]
        # Downtime consumes wall-clock budget; a restart cannot create more time.
        self.start_time -= max(0.0, time.time() - self.state["started_at"])
        self.save()

    @staticmethod
    def _write(path, value):
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def save(self, status=None):
        if status is not None:
            self.state["status"] = status
        self.state["output_tokens"] = self.total_output_tokens
        self._write(self.work_dir / self.STATE_FILE, self.state)

    def add_output_tokens(self, n):
        super().add_output_tokens(n)
        self.save()
