# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

from dataclasses import dataclass
from enum import Flag, auto
from typing import List, Optional, TextIO, Dict


class GpioFlag(Flag):
	ACTIVE_HIGH = 0
	ACTIVE_LOW = auto()


@dataclass(init=False)
class Options:
	dtb: List[TextIO]
	regulator: Optional[List[str]]
	backlight: bool
	backlight_gpio: bool
	dcs_get_brightness: bool
	ignore_wait: int
	use_helper: bool
	dumb_dcs: bool

	# Added by panel driver generator
	compatible: str
	gpios: Dict[str, GpioFlag]
