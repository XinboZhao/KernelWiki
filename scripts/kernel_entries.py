#!/usr/bin/env python3

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CUDA_EXTENSIONS = {".cu", ".cuh", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inl"}


@dataclass(frozen=True)
class KernelEntry:
    name: str
    kind: str
    body_sha256: str
    line: int

    @property
    def semantic_key(self) -> tuple[str, str, str]:
        return self.kind, self.name, self.body_sha256

    def manifest_record(self) -> dict[str, str]:
        return {
            "name": self.name,
            "kind": self.kind,
            "body_sha256": self.body_sha256,
        }


def decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def python_kernel_entries(text: str) -> list[KernelEntry]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    entries = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = {decorator_name(item) for item in node.decorator_list}
        if any(name.endswith("cute.kernel") for name in decorators):
            kind = "cute_kernel"
        elif any(name.endswith("triton.jit") for name in decorators):
            kind = "triton_jit"
        else:
            continue
        body = ast.dump(
            ast.Module(body=node.body, type_ignores=[]),
            annotate_fields=True,
            include_attributes=False,
        )
        entry = KernelEntry(
            name=node.name,
            kind=kind,
            body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            line=min(
                [item.lineno for item in node.decorator_list if hasattr(item, "lineno")]
                or [node.lineno]
            ),
        )
        if entry.semantic_key not in seen:
            seen.add(entry.semantic_key)
            entries.append(entry)
    return sorted(entries, key=lambda item: (item.line, item.name, item.body_sha256))


def mask_cpp(text: str) -> str:
    """Hide comments/literals without changing source offsets or line numbers."""
    token = re.compile(
        r'R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})\(.*?\)(?P=delimiter)"'
        r'|//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
        flags=re.DOTALL,
    )
    return token.sub(lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()), text)


def cuda_kernel_entries(text: str) -> list[KernelEntry]:
    syntax_text = mask_cpp(text)
    entries = []
    seen = set()
    for marker in re.finditer(r"\b__global__\b", syntax_text):
        terminator = re.search(r"[;{]", syntax_text[marker.end() :])
        if not terminator or terminator.group() != "{":
            continue
        body_start = marker.end() + terminator.start()
        calls = re.findall(
            r"([A-Za-z_]\w*)\s*\(", syntax_text[marker.end() : body_start]
        )
        if not calls:
            continue
        depth = 0
        body_end = None
        for index in range(body_start, len(syntax_text)):
            if syntax_text[index] == "{":
                depth += 1
            elif syntax_text[index] == "}":
                depth -= 1
                if depth == 0:
                    body_end = index + 1
                    break
        if body_end is None:
            continue
        body = text[body_start:body_end]
        body = re.sub(r"//.*?$|/\*.*?\*/", "", body, flags=re.MULTILINE | re.DOTALL)
        body = re.sub(r"\s+", "", body)
        if body == "{}":
            continue
        entry = KernelEntry(
            name=calls[-1],
            kind="cuda_global",
            body_sha256=hashlib.sha256(body.encode()).hexdigest(),
            line=text[: marker.start()].count("\n") + 1,
        )
        if entry.semantic_key not in seen:
            seen.add(entry.semantic_key)
            entries.append(entry)
    return sorted(entries, key=lambda item: (item.line, item.name, item.body_sha256))


def kernel_entries(path: Path, text: Optional[str] = None) -> list[KernelEntry]:
    if text is None:
        text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return python_kernel_entries(text)
    if path.suffix in CUDA_EXTENSIONS:
        return cuda_kernel_entries(text)
    return []


def kernel_snippet(path: Path, name: str, line: int) -> str:
    """Render only the selected definition, never other candidates in its file."""
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines(keepends=True)
    if path.suffix == '.py':
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                first = min([d.lineno for d in node.decorator_list] or [node.lineno])
                if first == line:
                    return ''.join(lines[first - 1:node.end_lineno])
    else:
        # Preserve offsets while hiding comments and strings for brace matching.
        masked = mask_cpp(text)
        offset = sum(len(item) for item in lines[:line - 1])
        marker = masked.find('__global__', offset)
        if marker >= 0:
            start = masked.find('{', marker)
            depth = 0
            for index in range(start, len(masked)):
                depth += (masked[index] == '{') - (masked[index] == '}')
                if depth == 0:
                    prefix_start = offset
                    boundary = max(masked.rfind('}', 0, marker), masked.rfind(';', 0, marker))
                    template = masked.rfind('template', boundary + 1, marker)
                    if template >= 0:
                        prefix_start = template
                    return text[prefix_start:index + 1] + '\n'
    raise ValueError(f'Cannot render selected entry {path}::{name}')
