#!/usr/bin/env python3
"""Bind a complete wheel and sdist to one checked-out release commit."""

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

MAX_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 20000
MANIFEST = "release-manifest.json"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def safe_member(name):
    value = PurePosixPath(name)
    require(name and not value.is_absolute() and ".." not in value.parts
            and "\\" not in name and "\x00" not in name, "archive-path-refused")


def identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def regular_snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
                "artifact-kind-or-size-refused")
        with os.fdopen(os.dup(fd), "rb") as stream:
            body = stream.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        require(len(body) == before.st_size and identity(before) == identity(after)
                == identity(path.lstat()), "artifact-changed")
        return body
    finally:
        os.close(fd)


def metadata(body, version):
    value = BytesParser().parsebytes(body)
    require(value["Name"] == "scitex-dev" and value["Version"] == version,
            "distribution-identity-mismatch")


def wheel_check(body, version):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        require(0 < len(members) <= MAX_MEMBERS and len(set(names)) == len(names),
                "wheel-membership-refused")
        require(sum(member.file_size for member in members) <= MAX_BYTES,
                "wheel-expanded-size-refused")
        for member in members:
            safe_member(member.filename)
            mode = member.external_attr >> 16
            require(not member.is_dir() and (not stat.S_IFMT(mode)
                    or stat.S_ISREG(mode)), "wheel-member-kind-refused")
        prefix = f"scitex_dev-{version}.dist-info/"
        metadata(archive.read(prefix + "METADATA"), version)
        records = list(csv.reader(io.StringIO(archive.read(prefix + "RECORD").decode())))
        require(all(len(row) == 3 for row in records), "wheel-record-shape-refused")
        require(len(records) == len(names) and len({row[0] for row in records}) == len(names)
                and {row[0] for row in records} == set(names), "wheel-record-membership-refused")
        for name, digest, size in records:
            payload = archive.read(name)
            if name == prefix + "RECORD":
                require(digest == size == "", "wheel-record-self-refused")
            else:
                expected = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
                require(digest == "sha256=" + expected and size == str(len(payload)),
                        "wheel-record-byte-mismatch")
        require(any(name.startswith("scitex_dev/") for name in names), "wheel-package-missing")


def sdist_check(body, version):
    prefix = f"scitex_dev-{version}/"
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        require(0 < len(members) <= MAX_MEMBERS and len(set(names)) == len(names),
                "sdist-membership-refused")
        require(sum(member.size for member in members) <= MAX_BYTES,
                "sdist-expanded-size-refused")
        for member in members:
            safe_member(member.name)
            require((member.name == prefix.rstrip("/") or member.name.startswith(prefix))
                    and (member.isreg() or member.isdir()), "sdist-member-kind-or-root-refused")
        metadata(archive.extractfile(prefix + "PKG-INFO").read(), version)


def artifact_manifest(root, tag, commit):
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is not None,
            "release-tag-refused")
    require(re.fullmatch(r"[a-f0-9]{40}", commit) is not None, "release-commit-refused")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=5).strip()
    require(actual == commit, "checkout-commit-mismatch")
    version = tag[1:]
    names = [f"scitex_dev-{version}-py3-none-any.whl", f"scitex_dev-{version}.tar.gz"]
    require(root.is_dir() and not root.is_symlink(), "distribution-root-refused")
    require({path.name for path in root.iterdir()} == set(names),
            "distribution-membership-mismatch")
    rows = []
    for name in names:
        body = regular_snapshot(root / name)
        (wheel_check if name.endswith(".whl") else sdist_check)(body, version)
        rows.append({"name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    return {"schema": 1, "project": "scitex-dev", "tag": tag,
            "version": version, "commit": commit, "files": rows}


def verify_oidc(jwt, commit):
    """Check declared claims locally; PyPI verifies the signed JWT itself."""
    require(re.fullmatch(r"[a-f0-9]{40}", commit) is not None, "workflow-commit-refused")
    parts = jwt.split(".")
    require(len(jwt) <= 65536 and len(parts) == 3
            and all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts),
            "oidc-token-shape-refused")
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    require(isinstance(claims, dict), "oidc-claims-shape-refused")
    workflow = "scitex-ai/scitex-dev/.github/workflows/pypi-publish-and-github-release-on-tag.yml@refs/heads/main"
    expected = {
        "iss": "https://token.actions.githubusercontent.com", "aud": "pypi",
        "repository": "scitex-ai/scitex-dev", "repository_owner": "scitex-ai",
        "sub": "repo:scitex-ai/scitex-dev:environment:pypi", "environment": "pypi",
        "ref": "refs/heads/main", "sha": commit, "event_name": "workflow_dispatch",
        "workflow_ref": workflow, "job_workflow_ref": workflow,
        "runner_environment": "self-hosted",
    }
    require(all(claims.get(key) == value for key, value in expected.items()),
            "oidc-publisher-claims-mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["write", "verify", "oidc"])
    parser.add_argument("--tag")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--dist", default="dist")
    args = parser.parse_args()
    if args.operation == "oidc":
        import sys

        verify_oidc(sys.stdin.read(65537), args.commit)
        print("OIDC-CLAIMS-OK: signature verification remains PyPI's responsibility")
        return
    require(args.tag is not None, "release-tag-required")
    root = Path(args.dist)
    result = artifact_manifest(root, args.tag, args.commit)
    path = root.parent / MANIFEST
    if args.operation == "write":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    else:
        require(json.loads(regular_snapshot(path)) == result, "release-manifest-mismatch")
    print(json.dumps({"verified": True, "tag": result["tag"], "commit": result["commit"],
                      "files": result["files"]}, sort_keys=True))


if __name__ == "__main__":
    main()
