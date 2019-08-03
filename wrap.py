# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

from typing import List


def _width(s: str) -> int:
	return len(s) + s.count('\t') * 7


def join(prefix: str, sep: str, end: str, items: List[str], force: int = -1, wrap: int = 80) -> str:
	s = prefix + (sep + ' ').join(items) + end
	if _width(s) <= wrap:
		return s

	align = _width(prefix)
	wrap -= align
	indent = '\t' * (align // 8) + ' ' * (align % 8)

	s = ''
	line = ''

	last = len(items) - 1
	for i, item in enumerate(items):
		if i == last:
			sep = end

		if line:
			if force == i or _width(line) + len(item) + len(sep) > wrap:
				s += prefix + line + '\n'
				prefix = indent
				line = ''
			else:
				line += ' '
		line += item + sep

	s += prefix + line
	return s
