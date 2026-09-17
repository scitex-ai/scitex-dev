"""Organization-wide freshness policy for GitHub and scitex-cards.

The cutoff is the contract: every backend receives the same UTC instant and
an item is stale only when ``updated_at < cutoff``. GitHub candidates are
re-read immediately before closing so an update racing the inventory wins.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

DEFAULT_FRESHNESS_DAYS = 3
DEFAULT_ORGANIZATION = "scitex-ai"


class FreshnessError(RuntimeError):
    """Base error for a freshness run."""


class GitHubTransportError(FreshnessError):
    """A GitHub API request failed after bounded retries."""


class CardsUnavailableError(FreshnessError):
    """Required scitex-cards integration is not installed."""


@dataclass(frozen=True)
class FreshnessPolicy:
    """Organization freshness policy defaults."""

    organization: str = DEFAULT_ORGANIZATION
    freshness_days: int = DEFAULT_FRESHNESS_DAYS

    def __post_init__(self) -> None:
        if self.freshness_days < 0:
            raise ValueError("freshness_days must be >= 0")
        if not self.organization.strip():
            raise ValueError("organization must not be empty")


@dataclass(frozen=True)
class GitHubItem:
    """One open issue or pull request in an organization repository."""

    repo: str
    number: int
    kind: str
    updated_at: datetime
    url: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {"issue", "pull_request"}:
            raise ValueError(f"unsupported GitHub item kind: {self.kind!r}")


@dataclass
class GitHubCounts:
    repositories: int = 0
    examined: int = 0
    issues_examined: int = 0
    pull_requests_examined: int = 0
    candidates: int = 0
    issues_candidates: int = 0
    pull_requests_candidates: int = 0
    closed: int = 0
    issues_closed: int = 0
    pull_requests_closed: int = 0
    freshened: int = 0
    no_longer_open: int = 0


@dataclass
class CardsResult:
    available: bool
    invoked: bool
    required: bool
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class FreshnessResult:
    organization: str
    freshness_days: int
    now: datetime
    cutoff: datetime
    dry_run: bool
    github: GitHubCounts
    cards: CardsResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "freshness_days": self.freshness_days,
            "now": format_utc(self.now),
            "cutoff": format_utc(self.cutoff),
            "dry_run": self.dry_run,
            "github": {"counts": asdict(self.github)},
            "cards": {
                "available": self.cards.available,
                "invoked": self.cards.invoked,
                "required": self.cards.required,
                "counts": dict(self.cards.counts),
            },
        }


class Transport(Protocol):
    def request(
        self, method: str, endpoint: str, *, fields: dict[str, Any] | None = None
    ) -> Any: ...


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return _aware_utc(datetime.fromisoformat(text))


def format_utc(value: datetime) -> str:
    value = _aware_utc(value)
    timespec = "microseconds" if value.microsecond else "seconds"
    return value.isoformat(timespec=timespec).replace("+00:00", "Z")


def compute_cutoff(
    now: datetime, freshness_days: int = DEFAULT_FRESHNESS_DAYS
) -> datetime:
    if freshness_days < 0:
        raise ValueError("freshness_days must be >= 0")
    return _aware_utc(now) - timedelta(days=freshness_days)


def is_stale(updated_at: datetime, cutoff: datetime) -> bool:
    """Strict comparison: the exact boundary remains fresh."""

    return _aware_utc(updated_at) < _aware_utc(cutoff)


class GhCliTransport:
    """Small ``gh api`` transport with bounded secondary-limit retries."""

    def __init__(
        self,
        *,
        run_fn: Callable[..., Any] = subprocess.run,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._run = run_fn
        self._sleep = sleep_fn
        self._max_attempts = max_attempts

    def request(
        self, method: str, endpoint: str, *, fields: dict[str, Any] | None = None
    ) -> Any:
        method = method.upper()
        argv = ["gh", "api", endpoint, "--method", method]
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": 60,
        }
        if fields is not None:
            argv += ["--input", "-"]
            kwargs["input"] = json.dumps(fields, sort_keys=True)

        last_message = ""
        attempt = 0
        for attempt in range(1, self._max_attempts + 1):
            try:
                proc = self._run(argv, **kwargs)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise GitHubTransportError(
                    f"GitHub transport unavailable: {exc}"
                ) from exc
            if proc.returncode == 0:
                try:
                    return json.loads(proc.stdout or "null")
                except json.JSONDecodeError as exc:
                    raise GitHubTransportError(
                        f"GitHub returned invalid JSON for {method} {endpoint}"
                    ) from exc

            last_message = (proc.stderr or proc.stdout or "").strip()
            if not _is_secondary_limit(last_message) or attempt == self._max_attempts:
                break
            self._sleep(float(2 ** (attempt - 1)))

        raise GitHubTransportError(
            f"GitHub {method} {endpoint} failed after {attempt} attempt(s): "
            f"{last_message[:500]}"
        )


def _is_secondary_limit(message: str) -> bool:
    lowered = message.lower()
    return "secondary rate limit" in lowered or "abuse detection" in lowered


class GitHubClient:
    """GitHub inventory and mutation boundary."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self.last_repository_count = 0

    @classmethod
    def from_gh(cls, **kwargs: Any) -> "GitHubClient":
        return cls(GhCliTransport(**kwargs))

    def list_open_items(self, organization: str) -> list[GitHubItem]:
        repos = self._list_pages(f"/orgs/{organization}/repos", extra="type=all")
        active_repos = sorted(
            str(repo["full_name"])
            for repo in repos
            if repo.get("full_name")
            and not repo.get("archived", False)
            and not repo.get("disabled", False)
        )
        self.last_repository_count = len(active_repos)

        items: list[GitHubItem] = []
        for repo in active_repos:
            raw_items = self._list_pages(f"/repos/{repo}/issues", extra="state=open")
            for raw in raw_items:
                kind = "pull_request" if "pull_request" in raw else "issue"
                items.append(
                    GitHubItem(
                        repo=repo,
                        number=int(raw["number"]),
                        kind=kind,
                        updated_at=parse_timestamp(raw["updated_at"]),
                        url=str(raw.get("html_url", "")),
                    )
                )
        return sorted(items, key=lambda item: (item.repo, item.number, item.kind))

    def _list_pages(self, base: str, *, extra: str = "") -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in base else "?"
            prefix = f"{base}{separator}"
            query = f"{extra}&" if extra else ""
            endpoint = f"{prefix}{query}per_page=100&page={page}"
            batch = self.transport.request("GET", endpoint)
            if not isinstance(batch, list):
                raise GitHubTransportError(
                    f"GitHub list endpoint returned non-list: {endpoint}"
                )
            output.extend(batch)
            if len(batch) < 100:
                return output
            page += 1

    def get(self, item: GitHubItem) -> GitHubItem | None:
        endpoint = self._item_endpoint(item)
        raw = self.transport.request("GET", endpoint)
        if isinstance(raw, list) and len(raw) == 1:
            raw = raw[0]
        if not isinstance(raw, dict):
            raise GitHubTransportError(
                f"GitHub item endpoint returned non-object: {endpoint}"
            )
        if raw.get("state") != "open":
            return None
        return GitHubItem(
            repo=item.repo,
            number=item.number,
            kind=item.kind,
            updated_at=parse_timestamp(raw["updated_at"]),
            url=str(raw.get("html_url", item.url)),
        )

    def close(self, item: GitHubItem) -> None:
        # No comments, labels, audit issues, or shadow files: state only.
        endpoint = self._item_endpoint(item)
        self.transport.request("PATCH", endpoint, fields={"state": "closed"})

    @staticmethod
    def _item_endpoint(item: GitHubItem) -> str:
        collection = "pulls" if item.kind == "pull_request" else "issues"
        return f"/repos/{item.repo}/{collection}/{item.number}"


def run_cards_freshness_gc(
    cutoff: datetime,
    *,
    dry_run: bool,
    required: bool,
    which_fn: Callable[[str], str | None] = shutil.which,
    run_fn: Callable[..., Any] = subprocess.run,
) -> CardsResult:
    executable = which_fn("scitex-cards")
    if executable is None:
        if required:
            raise CardsUnavailableError(
                "scitex-cards freshness-gc was requested but scitex-cards is unavailable"
            )
        return CardsResult(available=False, invoked=False, required=False)

    argv = [executable, "freshness-gc", "--cutoff", format_utc(cutoff), "--json"]
    if dry_run:
        argv.append("--dry-run")
    proc = run_fn(argv, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise FreshnessError(
            "scitex-cards freshness-gc failed "
            f"(exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise FreshnessError("scitex-cards freshness-gc returned invalid JSON") from exc
    counts = {
        str(key): int(value)
        for key, value in payload.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    return CardsResult(available=True, invoked=True, required=required, counts=counts)


def cards_cli_available(
    *,
    which_fn: Callable[[str], str | None] = shutil.which,
    run_fn: Callable[..., Any] = subprocess.run,
) -> bool:
    """Return whether the cutoff-driven Cards interface is callable."""
    executable = which_fn("scitex-cards")
    if executable is None:
        return False
    try:
        proc = run_fn(
            [executable, "freshness-gc", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def run_freshness_gc(
    *,
    policy: FreshnessPolicy,
    now: datetime,
    dry_run: bool,
    github: GitHubClient | None = None,
    list_items_fn: Callable[[str], list[GitHubItem]] | None = None,
    cards_mode: str = "auto",
    cards_fn: Callable[..., CardsResult] = run_cards_freshness_gc,
    cards_available_fn: Callable[[], bool] = cards_cli_available,
) -> FreshnessResult:
    """Apply one deterministic cutoff to GitHub and Cards."""

    if cards_mode not in {"auto", "required", "off"}:
        raise ValueError("cards_mode must be auto, required, or off")
    now = _aware_utc(now)
    cutoff = compute_cutoff(now, policy.freshness_days)
    cards_available = cards_mode != "off" and cards_available_fn()
    if cards_mode == "required" and not cards_available:
        raise CardsUnavailableError(
            "scitex-cards freshness-gc was requested but scitex-cards is unavailable"
        )
    github = github or GitHubClient.from_gh()
    inventory = (list_items_fn or github.list_open_items)(policy.organization)
    inventory = sorted(inventory, key=lambda item: (item.repo, item.number, item.kind))

    counts = GitHubCounts(
        repositories=github.last_repository_count,
        examined=len(inventory),
        issues_examined=sum(item.kind == "issue" for item in inventory),
        pull_requests_examined=sum(item.kind == "pull_request" for item in inventory),
    )
    candidates = [item for item in inventory if is_stale(item.updated_at, cutoff)]
    counts.candidates = len(candidates)
    counts.issues_candidates = sum(item.kind == "issue" for item in candidates)
    counts.pull_requests_candidates = sum(
        item.kind == "pull_request" for item in candidates
    )

    if not dry_run:
        for item in candidates:
            current = github.get(item)
            if current is None:
                counts.no_longer_open += 1
                continue
            if not is_stale(current.updated_at, cutoff):
                counts.freshened += 1
                continue
            github.close(current)
            counts.closed += 1
            if current.kind == "issue":
                counts.issues_closed += 1
            else:
                counts.pull_requests_closed += 1

    if cards_mode == "off" or not cards_available:
        cards = CardsResult(available=False, invoked=False, required=False)
    else:
        cards = cards_fn(
            cutoff,
            dry_run=dry_run,
            required=cards_mode == "required",
        )

    return FreshnessResult(
        organization=policy.organization,
        freshness_days=policy.freshness_days,
        now=now,
        cutoff=cutoff,
        dry_run=dry_run,
        github=counts,
        cards=cards,
    )


__all__ = [
    "CardsResult",
    "CardsUnavailableError",
    "DEFAULT_FRESHNESS_DAYS",
    "DEFAULT_ORGANIZATION",
    "FreshnessError",
    "FreshnessPolicy",
    "FreshnessResult",
    "GhCliTransport",
    "GitHubClient",
    "GitHubCounts",
    "GitHubItem",
    "GitHubTransportError",
    "compute_cutoff",
    "cards_cli_available",
    "format_utc",
    "is_stale",
    "parse_timestamp",
    "run_cards_freshness_gc",
    "run_freshness_gc",
]
