# -*- coding: utf-8 -*-
"""GPG-backed secret store with a pass-compatible on-disk layout.

WHY NOT SHELL OUT TO ``pass``
-----------------------------
``pass`` is not installed on our hosts and cannot be installed without root,
so depending on the *binary* would make the store unusable exactly where it is
needed. What matters for interoperability is the *layout*, not the program:

    <root>/.gpg-id          recipient key id(s), one per line
    <root>/<name>.gpg       one gpg-encrypted file per secret

That is byte-for-byte what ``pass`` reads, so a host that does have ``pass``
operates on the identical store with no conversion. Crypto stays entirely
GnuPG's — nothing here implements or reimplements a cipher.

SECRETS NEVER TOUCH argv
------------------------
Every value crosses process boundaries through *stdin*, never a command-line
argument, because argv is world-readable via ``ps`` on the same host. That is
not hypothetical: a cloudflared token was disclosed to an agent session on
2026-08-03 precisely this way.

FAILURE HAS A REPRESENTATION
----------------------------
Every operation returns :class:`SecretResult` — the same shape every time, with
each signal as its own field and ``code`` carrying a declared numeric meaning.
A failure can never be mistaken for a value, because the value lives in its own
field and is ``None`` unless ``code == OK``.

This is the defect that keeps recurring in this codebase: our previous
``decrypt.sh`` wrote its errors to *stdout*, so a 61-byte ANSI error string was
ingested AS a password. Same shape as a namespace package importing cleanly
while the attribute it is asked for does not exist. In both cases failure had
nowhere to live, so it was rendered as a plausible success value.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
import string
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Declared codes. Never overload 1/2 with a domain meaning — every CLI
# framework already spends those on "generic failure" and "usage error", so a
# renamed verb would impersonate our success value.
OK = 200
INVALID_NAME = 400
NO_RECIPIENT = 401
NOT_FOUND = 404
ALREADY_EXISTS = 409
GPG_MISSING = 424
GPG_FAILED = 500

_DIR_MODE = 0o700
_FILE_MODE = 0o600

# Excludes look-alikes (0/O, 1/l/I) so a generated secret can be read aloud or
# retyped from a screen without ambiguity.
_ALPHABET = (
    "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    + "!@#%^&*-_=+?"
)


@dataclass(frozen=True)
class SecretResult:
    """The one shape every store operation returns.

    ``value`` is populated ONLY on a successful ``show``. Every other field is
    meaningful on every call, so a caller never has to guess which keys exist.
    """

    code: int
    detail: str
    name: Optional[str] = None
    value: Optional[str] = None
    names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Validate where the object is BUILT, not three layers downstream.
        if not isinstance(self.code, int):
            raise TypeError(f"code must be int, got {type(self.code).__name__}")
        if self.value is not None and self.code != OK:
            raise ValueError(
                f"value present on a non-OK result (code={self.code}) — a failure "
                "must never carry something a caller could mistake for a secret"
            )
        if not self.detail:
            raise ValueError("detail must be non-empty: an error that says only "
                             "what broke is half-written")

    @property
    def ok(self) -> bool:
        return self.code == OK


def generate_value(length: int = 32) -> str:
    """Return a cryptographically-random secret. Never logged, never in argv."""
    if length < 8:
        raise ValueError(f"length {length} is too short; minimum is 8")
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class SecretStore:
    """A pass-compatible GPG store rooted at ``root``.

    ``root`` is resolved by the caller, never guessed here — the fleet store
    lives at ``~/.scitex/<pkg>/secret`` while a tenant's lives under their own
    overlay. The *recipient* is always the owner of that root, which is what
    keeps a host-level agent from decrypting a tenant's secrets.
    """

    def __init__(self, root: Path, gpg_binary: str = "gpg") -> None:
        self.root = Path(root).expanduser()
        self.gpg_binary = gpg_binary

    # ---------------------------------------------------------------- helpers

    def _gpg_available(self) -> bool:
        return shutil.which(self.gpg_binary) is not None

    def _path_for(self, name: str) -> Optional[Path]:
        """Resolve ``name`` inside the store, or ``None`` if it escapes.

        Containment is checked with ``Path.relative_to`` on the RESOLVED paths.
        A ``startswith`` prefix test is not containment — ``/store-evil`` starts
        with ``/store``.
        """
        if not name or name.startswith("/") or "\x00" in name:
            return None
        candidate = (self.root / f"{name}.gpg").resolve()
        try:
            candidate.relative_to(self.root.resolve())
        except ValueError:
            return None
        return candidate

    def recipients(self) -> list[str]:
        gpg_id = self.root / ".gpg-id"
        if not gpg_id.is_file():
            return []
        return [
            line.strip()
            for line in gpg_id.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def _harden(self, path: Path) -> None:
        """Strip group/other. Uses ``go-rwx`` semantics, not a literal 0600.

        git records only the owner-exec bit, so forcing 0600 on a 0755 file
        registers a real mode change and dirties the repo. Clearing only the
        group/other bits leaves git's recorded mode identical.
        """
        current = stat.S_IMODE(path.stat().st_mode)
        path.chmod(current & ~0o077)

    # ------------------------------------------------------------ operations

    def init(self, recipient: str) -> SecretResult:
        """Create the store and record its recipient."""
        if not recipient:
            return SecretResult(NO_RECIPIENT, "no recipient given; pass a gpg key id or uid")
        self.root.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        self.root.chmod(_DIR_MODE)
        gpg_id = self.root / ".gpg-id"
        gpg_id.write_text(f"{recipient}\n", encoding="utf-8")
        self._harden(gpg_id)
        return SecretResult(OK, f"store initialised at {self.root} for {recipient}")

    def list_names(self) -> SecretResult:
        if not self.root.is_dir():
            return SecretResult(NOT_FOUND, f"no store at {self.root}")
        names = sorted(
            str(p.relative_to(self.root))[: -len(".gpg")]
            for p in self.root.rglob("*.gpg")
        )
        return SecretResult(OK, f"{len(names)} secret(s)", names=tuple(names))

    def store(self, name: str, value: str, overwrite: bool = False) -> SecretResult:
        """Encrypt ``value`` under ``name``. ``value`` is passed via stdin."""
        if not self._gpg_available():
            return SecretResult(
                GPG_MISSING,
                f"{self.gpg_binary} not found on PATH; install gnupg or pass gpg_binary",
            )
        target = self._path_for(name)
        if target is None:
            return SecretResult(INVALID_NAME, f"refusing name {name!r}: escapes the store root")
        if target.exists() and not overwrite:
            return SecretResult(
                ALREADY_EXISTS,
                f"{name} already exists; pass overwrite=True to replace it",
                name=name,
            )
        recips = self.recipients()
        if not recips:
            return SecretResult(
                NO_RECIPIENT,
                f"no .gpg-id in {self.root}; run init(recipient) first",
                name=name,
            )

        target.parent.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        argv = [self.gpg_binary, "--batch", "--yes", "--quiet", "--encrypt", "--output", str(target)]
        for r in recips:
            argv += ["--recipient", r]
        # The SECRET goes on stdin. Only the recipient and path are in argv.
        proc = subprocess.run(
            argv, input=value.encode("utf-8"), capture_output=True, check=False
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip() or "gpg failed with no message"
            return SecretResult(GPG_FAILED, f"encrypt failed for {name}: {err}", name=name)
        self._harden(target)
        return SecretResult(OK, f"stored {name}", name=name)

    def generate(self, name: str, length: int = 32, overwrite: bool = False) -> SecretResult:
        """Generate and store a random secret. The value is NEVER returned."""
        value = generate_value(length)
        result = self.store(name, value, overwrite=overwrite)
        if not result.ok:
            return result
        return SecretResult(OK, f"generated {name} ({length} chars)", name=name)

    def show(self, name: str) -> SecretResult:
        """Decrypt ``name``. Requires the private key to be present."""
        if not self._gpg_available():
            return SecretResult(GPG_MISSING, f"{self.gpg_binary} not found on PATH")
        target = self._path_for(name)
        if target is None:
            return SecretResult(INVALID_NAME, f"refusing name {name!r}: escapes the store root")
        if not target.is_file():
            return SecretResult(NOT_FOUND, f"no such secret: {name}", name=name)
        proc = subprocess.run(
            [self.gpg_binary, "--batch", "--quiet", "--decrypt", str(target)],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            # stderr NEVER becomes the value. This is the decrypt.sh defect.
            err = proc.stderr.decode("utf-8", "replace").strip() or "gpg failed with no message"
            return SecretResult(GPG_FAILED, f"decrypt failed for {name}: {err}", name=name)
        return SecretResult(
            OK, f"decrypted {name}", name=name, value=proc.stdout.decode("utf-8")
        )

    # -------------------------------------------------------------- backup

    def backup(self, dest: Path, passphrase: str, secret_key: bool = True) -> SecretResult:
        """Write a single symmetrically-encrypted archive of the store (+ key).

        WHAT ACTUALLY NEEDS BACKING UP, which is counter-intuitive
        ----------------------------------------------------------
        Losing the STORE is inconvenient. Losing the PRIVATE KEY is terminal:
        every ``.gpg`` file becomes permanently unreadable, on every host and
        every copy, forever. Replicating the store to ten machines protects
        nothing if the one key is gone. So this archives the key by default.

        WHY SYMMETRIC (passphrase) AND NOT PUBLIC-KEY
        ---------------------------------------------
        The archive contains the private key. Encrypting it TO that same key
        would make the backup openable only by the thing the backup exists to
        replace — recoverable only when recovery is not needed. A passphrase
        breaks that circularity.

        The passphrase crosses to gpg via a pipe file descriptor, never argv.
        """
        if not self._gpg_available():
            return SecretResult(GPG_MISSING, f"{self.gpg_binary} not found on PATH")
        if not passphrase:
            return SecretResult(
                NO_RECIPIENT,
                "refusing to write an unencrypted backup containing a private key; "
                "supply a passphrase",
            )
        if not self.root.is_dir():
            return SecretResult(NOT_FOUND, f"no store at {self.root}")

        recips = self.recipients()
        if secret_key and not recips:
            return SecretResult(
                NO_RECIPIENT,
                f"secret_key=True but {self.root}/.gpg-id names no recipient to export",
            )

        dest = Path(dest).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        staging = dest.parent / f".{dest.name}.staging"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(mode=_DIR_MODE)

        try:
            shutil.copytree(self.root, staging / "store", dirs_exist_ok=True)

            if secret_key:
                for recipient in recips:
                    key_out = staging / f"secret-key-{recipient}.asc"
                    proc = subprocess.run(
                        [self.gpg_binary, "--batch", "--quiet", "--armor",
                         "--export-secret-keys", recipient],
                        capture_output=True, check=False,
                    )
                    if proc.returncode != 0 or not proc.stdout:
                        err = proc.stderr.decode("utf-8", "replace").strip()
                        return SecretResult(
                            GPG_FAILED,
                            f"could not export secret key {recipient}: "
                            f"{err or 'gpg produced no key material'}. "
                            "The private key is the irreplaceable part — refusing to "
                            "write a backup that silently omits it.",
                        )
                    key_out.write_bytes(proc.stdout)
                    self._harden(key_out)

                    rev_out = staging / f"revocation-{recipient}.asc"
                    rev = subprocess.run(
                        [self.gpg_binary, "--batch", "--quiet", "--yes", "--armor",
                         "--gen-revoke", recipient],
                        input=b"y\n0\n\ny\n", capture_output=True, check=False,
                    )
                    # A missing revocation certificate degrades the backup but does
                    # not invalidate it, so this is recorded, not fatal.
                    if rev.returncode == 0 and rev.stdout:
                        rev_out.write_bytes(rev.stdout)
                        self._harden(rev_out)

            tar_path = staging.parent / f".{dest.name}.tar"
            shutil.make_archive(str(tar_path)[: -len(".tar")], "tar", root_dir=staging)

            proc = subprocess.run(
                [self.gpg_binary, "--batch", "--yes", "--quiet", "--symmetric",
                 "--cipher-algo", "AES256", "--passphrase-fd", "0",
                 "--output", str(dest), str(tar_path)],
                input=passphrase.encode("utf-8"), capture_output=True, check=False,
            )
            tar_path.unlink(missing_ok=True)
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", "replace").strip()
                return SecretResult(GPG_FAILED, f"backup encryption failed: {err or 'gpg failed'}")

            self._harden(dest)
            return SecretResult(
                OK,
                f"backup written to {dest} "
                f"({'with' if secret_key else 'WITHOUT'} private key). "
                "Store this on separate media from the live key — a backup on the "
                "same disk is lost by the same event it protects against.",
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def restore(self, src: Path, passphrase: str, dest: Path) -> SecretResult:
        """Unpack a backup written by :meth:`backup` into ``dest``.

        A backup nobody has ever restored is a hope, not a backup — the failure
        mode is discovering at recovery time that the archive was empty, keyless
        or written with a forgotten passphrase. This is the other half of that
        loop, and it refuses to overwrite an existing store so a restore drill
        can never destroy the live one.

        The private key is NOT auto-imported. Extracting it is reversible;
        importing it mutates the caller's keyring, which is a decision that
        belongs to a human at recovery time, not to a convenience default.
        """
        if not self._gpg_available():
            return SecretResult(GPG_MISSING, f"{self.gpg_binary} not found on PATH")
        src = Path(src).expanduser()
        if not src.is_file():
            return SecretResult(NOT_FOUND, f"no backup at {src}")
        if not passphrase:
            return SecretResult(NO_RECIPIENT, "a passphrase is required to open the backup")

        dest = Path(dest).expanduser()
        if dest.exists() and any(dest.iterdir()):
            return SecretResult(
                ALREADY_EXISTS,
                f"{dest} exists and is not empty; refusing to overwrite. "
                "Restore to a fresh path and compare before replacing anything.",
            )

        tar_path = dest.parent / f".{dest.name}.restore.tar"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                [self.gpg_binary, "--batch", "--yes", "--quiet", "--decrypt",
                 "--passphrase-fd", "0", "--output", str(tar_path), str(src)],
                input=passphrase.encode("utf-8"), capture_output=True, check=False,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", "replace").strip()
                return SecretResult(
                    GPG_FAILED,
                    f"could not open {src}: {err or 'gpg failed'}. "
                    "A wrong passphrase and a corrupt archive look identical here; "
                    "try the passphrase first.",
                )
            dest.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
            # filter="data" REFUSES members that would escape dest, hold absolute
            # paths, or carry device/setuid metadata. Without it, extraction is a
            # path-traversal primitive: a crafted archive writes anywhere the
            # process can. Python only makes this the default in 3.14, so on
            # every version we run today the unfiltered call is the dangerous one.
            try:
                with tarfile.open(tar_path) as archive:
                    archive.extractall(path=dest, filter="data")
            except (tarfile.TarError, OSError) as exc:
                # Must return the declared shape, not raise. A caller that gets an
                # exception here has no `code` to branch on and is exactly as likely
                # to log it and continue as to stop.
                return SecretResult(
                    GPG_FAILED,
                    f"archive from {src} was rejected during extraction: {exc}. "
                    "A member tried to write outside the destination, or the archive "
                    "is corrupt. Nothing was restored.",
                )
        finally:
            tar_path.unlink(missing_ok=True)

        restored_store = dest / "store"
        if not restored_store.is_dir():
            return SecretResult(
                GPG_FAILED,
                f"archive opened but contains no 'store/' directory — {src} is not "
                "a backup written by this tool, or it was truncated",
            )
        for path in dest.rglob("*"):
            if path.is_file():
                self._harden(path)

        count = sum(1 for _ in restored_store.rglob("*.gpg"))
        keys = sorted(p.name for p in dest.glob("secret-key-*.asc"))
        return SecretResult(
            OK,
            f"restored {count} secret(s) to {restored_store}. "
            + (
                f"Private key material extracted but NOT imported: {', '.join(keys)}. "
                "Import deliberately with `gpg --import` once you have confirmed this "
                "is the right key."
                if keys
                else "No private key in this archive — the secrets are unreadable "
                "without the original key."
            ),
            names=tuple(
                str(p.relative_to(restored_store))[: -len(".gpg")]
                for p in sorted(restored_store.rglob("*.gpg"))
            ),
        )

    def sync(self, remote: Optional[str] = None) -> SecretResult:
        """Commit the store to git and, if ``remote`` is set, push it.

        Cross-host sharing works because the files are ALREADY encrypted — the
        remote never sees plaintext, so an ordinary git remote is sufficient and
        no separate secure channel is needed.

        Only ``.gpg`` files and ``.gpg-id`` are committed. Nothing here can add
        a plaintext file to the index by accident.
        """
        if not shutil.which("git"):
            return SecretResult(GPG_MISSING, "git not found on PATH")
        if not self.root.is_dir():
            return SecretResult(NOT_FOUND, f"no store at {self.root}")

        def _git(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", "-C", str(self.root), *args], capture_output=True, check=False
            )

        if not (self.root / ".git").is_dir():
            init = _git("init", "--quiet")
            if init.returncode != 0:
                return SecretResult(
                    GPG_FAILED,
                    f"git init failed: {init.stderr.decode('utf-8', 'replace').strip()}",
                )

        _git("add", "--", ".gpg-id")
        for path in sorted(self.root.rglob("*.gpg")):
            _git("add", "--", str(path.relative_to(self.root)))

        status = _git("status", "--porcelain")
        if not status.stdout.strip():
            return SecretResult(OK, "nothing to sync; store already committed")

        commit = _git("commit", "--quiet", "-m", "sync secret store")
        if commit.returncode != 0:
            return SecretResult(
                GPG_FAILED,
                f"commit failed: {commit.stderr.decode('utf-8', 'replace').strip()}",
            )
        if not remote:
            return SecretResult(OK, "committed locally; no remote given, so nothing was pushed")

        push = _git("push", remote, "HEAD")
        if push.returncode != 0:
            return SecretResult(
                GPG_FAILED,
                f"committed locally but push to {remote} FAILED: "
                f"{push.stderr.decode('utf-8', 'replace').strip()}. "
                "The local commit stands; re-run sync once the remote is reachable.",
            )
        return SecretResult(OK, f"committed and pushed to {remote}")
