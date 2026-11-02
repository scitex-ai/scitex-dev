"""Resolve owned source bindings without importing or executing a package."""

from __future__ import annotations

import ast
from pathlib import Path


class UnprovenBinding(ValueError):
    """Source evidence is absent, unsafe, dynamic, or outside this repository."""


def read_source(repo: Path, path: Path) -> str:
    relative = path.relative_to(repo)
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnprovenBinding(
                f"source symlink is not an owned regular file: {relative}"
            )
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise UnprovenBinding(f"source is absent or exceeds 4 MiB: {relative}")
    return path.read_text(encoding="utf-8")


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def meaningful(node) -> bool:
    """Reject empty/docstring/pass/constant/NotImplemented-only function bodies."""
    if isinstance(node, ast.ClassDef):
        return any(
            meaningful(item)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    body = [
        item
        for item in node.body
        if not (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        )
    ]
    for item in body:
        if isinstance(item, ast.Pass):
            continue
        if (
            isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
            and item.value.value is Ellipsis
        ):
            continue
        if isinstance(item, ast.Raise):
            exc = item.exc.func if isinstance(item.exc, ast.Call) else item.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        if isinstance(item, ast.Return) and (
            item.value is None or isinstance(item.value, ast.Constant)
        ):
            continue
        return True
    return False


class SourceTree:
    """Finite source resolver for ordinary imports, aliases and lazy export maps."""

    def __init__(self, repo: Path, overlays=None):
        self.repo = repo.resolve()
        self._cache = {}
        self.overlays = overlays

    def exists(self, path):
        if self.overlays is not None:
            return path.relative_to(self.repo).as_posix() in self.overlays
        return path.exists() or path.is_symlink()

    def read(self, path):
        if self.overlays is None:
            return read_source(self.repo, path)
        value = self.overlays.get(path.relative_to(self.repo).as_posix())
        if not isinstance(value, str) or len(value.encode("utf-8")) > 4 * 1024 * 1024:
            raise UnprovenBinding("staged source is absent, nonregular or oversized")
        return value

    def module(self, name: str):
        if not name or any(not part.isidentifier() for part in name.split(".")):
            raise UnprovenBinding("invalid Python module name")
        for base in (self.repo / "src", self.repo):
            stem = base.joinpath(*name.split("."))
            for path in (stem.with_suffix(".py"), stem / "__init__.py"):
                if self.exists(path):
                    if path not in self._cache:
                        try:
                            self._cache[path] = ast.parse(self.read(path))
                        except (OSError, UnicodeError, SyntaxError) as exc:
                            raise UnprovenBinding(
                                f"cannot parse owned source: {path.relative_to(self.repo)}"
                            ) from exc
                    return path, self._cache[path]
        raise UnprovenBinding(f"owned source module not found: {name}")

    @staticmethod
    def assignments(tree):
        for node in tree.body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, ast.AnnAssign)
                else []
            )
            for target in targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value

    def resolve(self, module: str, name: str, seen=()):
        key = (module, name)
        if key in seen or len(seen) >= 16:
            raise UnprovenBinding("cyclic or excessively deep source binding")
        path, tree = self.module(module)
        next_seen = (*seen, key)
        for node in reversed(tree.body):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, ast.AnnAssign)
                else []
            )
            if any(
                isinstance(target, ast.Name) and target.id == name for target in targets
            ):
                if isinstance(node.value, ast.Name):
                    return self.resolve(module, node.value.id, next_seen)
                return path, tree, node.value
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == name
            ):
                return path, tree, node
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if (alias.asname or alias.name) != name:
                        continue
                    package = (
                        module.split(".")
                        if path.name == "__init__.py"
                        else module.split(".")[:-1]
                    )
                    if node.level:
                        if node.level > len(package):
                            raise UnprovenBinding(
                                "relative import escapes owned package"
                            )
                        parent = package[: len(package) - node.level + 1]
                        imported = ".".join(
                            [*parent, *str(node.module or "").split(".")]
                        ).strip(".")
                    else:
                        imported = node.module or ""
                    return self.resolve(imported, alias.name, next_seen)
        for target, value in self.assignments(tree):
            if target == name:
                if isinstance(value, ast.Name):
                    return self.resolve(module, value.id, next_seen)
                return path, tree, value
        # PEP-562 evidence includes the actual map lookup/import/getattr/return
        # chain, not merely a decorative dictionary mentioned by a getter.
        for target, value in self.assignments(tree):
            mapping = literal(value)
            if not isinstance(mapping, dict) or name not in mapping:
                continue
            if not _lazy_export_chain(tree, target):
                continue
            dest = mapping[name]
            if isinstance(dest, str):
                return self.resolve(f"{module}.{dest.lstrip('.')}", name, next_seen)
            raise UnprovenBinding(f"dynamic lazy export: {module}:{name}")
        raise UnprovenBinding(f"owned source binding not found: {module}:{name}")

    def exports(self, module: str):
        _path, tree = self.module(module)
        for name, value in self.assignments(tree):
            if name == "__all__":
                result = literal(value)
                if not isinstance(result, (list, tuple)) or not all(
                    isinstance(x, str) for x in result
                ):
                    raise UnprovenBinding("dynamic __all__ cannot be proven statically")
                return [x for x in result if not x.startswith("_")]
        return [
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not n.name.startswith("_")
        ]


def _lazy_export_chain(tree, mapping):
    for getter in tree.body:
        if (
            not isinstance(getter, ast.FunctionDef)
            or getter.name != "__getattr__"
            or not getter.args.args
        ):
            continue
        parameter = getter.args.args[0].arg
        lookup_variables = set()
        attributes = set()
        import_aliases = {
            a.asname or a.name
            for n in ast.walk(getter)
            if isinstance(n, ast.ImportFrom) and n.module == "importlib"
            for a in n.names
            if a.name == "import_module"
        }
        import_aliases.update(
            a.asname or a.name
            for n in tree.body
            if isinstance(n, ast.ImportFrom) and n.module == "importlib"
            for a in n.names
            if a.name == "import_module"
        )
        for node in ast.walk(getter):
            if (
                not isinstance(node, ast.Assign)
                or len(node.targets) != 1
                or not isinstance(node.targets[0], ast.Name)
            ):
                continue
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == mapping
                and value.func.attr == "get"
                and value.args
                and isinstance(value.args[0], ast.Name)
                and value.args[0].id == parameter
            ):
                lookup_variables.add(node.targets[0].id)
            if (
                isinstance(value, ast.Subscript)
                and isinstance(value.value, ast.Name)
                and value.value.id == mapping
                and isinstance(value.slice, ast.Name)
                and value.slice.id == parameter
            ):
                lookup_variables.add(node.targets[0].id)
        for node in ast.walk(getter):
            value = node.value if isinstance(node, (ast.Assign, ast.Return)) else None
            if (
                not isinstance(value, ast.Call)
                or not isinstance(value.func, ast.Name)
                or value.func.id != "getattr"
                or len(value.args) < 2
            ):
                continue
            imported, attr = value.args[:2]
            if (
                not isinstance(attr, ast.Name)
                or attr.id != parameter
                or not isinstance(imported, ast.Call)
                or not isinstance(imported.func, ast.Name)
                or imported.func.id not in import_aliases
                or not imported.args
            ):
                continue
            spec = imported.args[0]
            if not isinstance(spec, ast.JoinedStr) or not any(
                isinstance(item, ast.FormattedValue)
                and isinstance(item.value, ast.Name)
                and item.value.id in lookup_variables
                for item in spec.values
            ):
                continue
            if isinstance(node, ast.Return):
                return True
            attributes.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if any(
            isinstance(n, ast.Return)
            and isinstance(n.value, ast.Name)
            and n.value.id in attributes
            for n in ast.walk(getter)
        ):
            return True
    return False
