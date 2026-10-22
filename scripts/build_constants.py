#!/usr/bin/env python3
"""Convert Baileys' WABinary/constants.ts into a Python module."""
import re
from pathlib import Path

SRC = Path("/home/z/my-project/Baileys/src/WABinary/constants.ts")
DST = Path("/home/z/my-project/baileys-py/baileys_py/binary/constants.py")


def extract_tags(text: str) -> dict:
    m = re.search(r"export const TAGS\s*=\s*\{(.*?)\}", text, re.DOTALL)
    out = {}
    for line in m.group(1).splitlines():
        m2 = re.match(r"\s*([A-Z_0-9]+)\s*:\s*([0-9]+)", line)
        if m2:
            out[m2.group(1)] = int(m2.group(2))
    return out


def extract_array(text: str, name: str) -> list:
    """Return list of inner arrays (each a list of strings).

    If the body has no nested ``[`` it is treated as a flat list (returned
    as a single-element outer list).
    """
    m = re.search(rf"export const {name}\s*=\s*(\[)", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"could not find {name}")
    start = m.end() - 1  # position of the opening '['
    depth = 0
    in_str = False
    str_char = None
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if c == "\\":
                continue
            if c == str_char:
                in_str = False
            continue
        if c == "'" or c == '"':
            in_str = True
            str_char = c
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise RuntimeError(f"unterminated array {name}")
    body = text[start + 1:end]

    has_nested = "[" in re.sub(r"'[^']*'", "", body)
    if not has_nested:
        # Flat array — extract all string literals.
        return [re.findall(r"'((?:[^'\\]|\\.)*)'", body)]

    outer = []
    depth = 0
    cur = ""
    in_str = False
    for c in body:
        if c == "'" or c == '"':
            in_str = not in_str
            cur += c
            continue
        if in_str:
            cur += c
            continue
        if c == "[":
            depth += 1
            if depth == 1:
                cur = ""
                continue
        if c == "]":
            depth -= 1
            if depth == 0:
                outer.append(cur)
                cur = ""
                continue
        cur += c

    parsed = []
    for inner_body in outer:
        inner_items = re.findall(r"'((?:[^'\\]|\\.)*)'", inner_body)
        parsed.append(inner_items)
    return parsed


def main() -> None:
    text = SRC.read_text()
    tags = extract_tags(text)
    single = extract_array(text, "SINGLE_BYTE_TOKENS")
    double = extract_array(text, "DOUBLE_BYTE_TOKENS")

    # `single` should be a list with one inner list (the array body)
    single_tokens = single[0] if single else []

    lines = []
    lines.append('"""Auto-generated WA binary protocol constants.')
    lines.append('')
    lines.append('Do not edit by hand — regenerate via scripts/build_constants.py.')
    lines.append('"""')
    lines.append('')
    lines.append("TAGS = {")
    for k, v in tags.items():
        lines.append(f"    {k!r}: {v},")
    lines.append("}")
    lines.append("")
    lines.append("SINGLE_BYTE_TOKENS = [")
    for tok in single_tokens:
        lines.append(f"    {tok!r},")
    lines.append("]")
    lines.append("")
    lines.append("DOUBLE_BYTE_TOKENS = [")
    for inner in double:
        lines.append("    [")
        for tok in inner:
            lines.append(f"        {tok!r},")
        lines.append("    ],")
    lines.append("]")
    lines.append("")
    lines.append("TOKEN_MAP = {}")
    lines.append("")
    lines.append("for _i, _tok in enumerate(SINGLE_BYTE_TOKENS):")
    lines.append("    TOKEN_MAP[_tok] = {'index': _i}")
    lines.append("")
    lines.append("for _i, _inner in enumerate(DOUBLE_BYTE_TOKENS):")
    lines.append("    for _j, _tok in enumerate(_inner):")
    lines.append("        TOKEN_MAP[_tok] = {'dict': _i, 'index': _j}")
    lines.append("")
    lines.append("__all__ = ['TAGS', 'SINGLE_BYTE_TOKENS', 'DOUBLE_BYTE_TOKENS', 'TOKEN_MAP']")
    lines.append("")

    DST.write_text("\n".join(lines))
    print(f"Wrote {DST} ({len(single_tokens)} single-byte tokens, "
          f"{sum(len(d) for d in double)} double-byte tokens)")


if __name__ == "__main__":
    main()
