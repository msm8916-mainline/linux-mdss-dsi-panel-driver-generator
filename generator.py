# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, TextIO


@dataclass(init=False)
class Options:
	dtb: List[TextIO]
	regulator: Optional[List[str]]
	backlight: bool
	backlight_gpio: bool
	ignore_wait: int
