# SPDX-License-Identifier: GPL-2.0-only
#
# Enums originally taken from:
# https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/include/video/mipi_display.h
#
# Defines for Mobile Industry Processor Interface (MIPI(R))
# Display Working Group standards: DSI, DCS, DBI, DPI
#
# Copyright (C) 2010 Guennadi Liakhovetski <g.liakhovetski@gmx.de>
# Copyright (C) 2006 Nokia Corporation
# Author: Imre Deak <imre.deak@nokia.com>
#
from __future__ import annotations

from enum import IntEnum, unique, Enum
from typing import List, Optional, Union, Tuple

from generator import Options

import wrap


def _hex_fill(i: int, size: int = 1) -> str:
	return f'{i:#0{size * 2 + 2}x}'


def _get_params_hex(b: bytes) -> List[str]:
	return [_hex_fill(i) for i in b]


def _get_params_int(size: int, byteorder: str):
	def _get_params(b: bytes) -> List[str]:
		if len(b) < size:
			return [_hex_fill(int.from_bytes(b, byteorder=byteorder), size)]

		itr = iter(b)
		return [_hex_fill(int.from_bytes(t, byteorder=byteorder), size) for t in zip(*[itr] * size)]

	return _get_params


@unique
class TearMode(IntEnum):
	VBLANK = 0
	VHBLANK = 1

	@property
	def identifier(self):
		return 'MIPI_DSI_DCS_TEAR_MODE_' + self.name

	@staticmethod
	def get_params(b: bytes) -> List[str]:
		return [TearMode(b[0]).identifier]


# MIPI DCS commands
@unique
class DCSCommand(Enum):
	NOP = 0x00, 0, 'mipi_dsi_dcs_nop'
	SOFT_RESET = 0x01, 0, 'mipi_dsi_dcs_soft_reset'
	# GET_COMPRESSION_MODE = 0x03,
	# GET_DISPLAY_ID = 0x04,
	# GET_ERROR_COUNT_ON_DSI = 0x05,
	# GET_RED_CHANNEL = 0x06,
	# GET_GREEN_CHANNEL = 0x07,
	# GET_BLUE_CHANNEL = 0x08,
	# GET_DISPLAY_STATUS = 0x09,
	# GET_POWER_MODE = 0x0A,
	# GET_ADDRESS_MODE = 0x0B,
	# GET_PIXEL_FORMAT = 0x0C,
	# GET_DISPLAY_MODE = 0x0D,
	# GET_SIGNAL_MODE = 0x0E,
	# GET_DIAGNOSTIC_RESULT = 0x0F,
	ENTER_SLEEP_MODE = 0x10, 0, 'mipi_dsi_dcs_enter_sleep_mode'
	EXIT_SLEEP_MODE = 0x11, 0, 'mipi_dsi_dcs_exit_sleep_mode'
	ENTER_PARTIAL_MODE = 0x12, 0,
	ENTER_NORMAL_MODE = 0x13, 0,
	# GET_IMAGE_CHECKSUM_RGB = 0x14,
	# GET_IMAGE_CHECKSUM_CT = 0x15,
	EXIT_INVERT_MODE = 0x20, 0,
	ENTER_INVERT_MODE = 0x21, 0,
	SET_GAMMA_CURVE = 0x26, 1,
	SET_DISPLAY_OFF = 0x28, 0, 'mipi_dsi_dcs_set_display_off'
	SET_DISPLAY_ON = 0x29, 0, 'mipi_dsi_dcs_set_display_on'
	SET_COLUMN_ADDRESS = 0x2A, 4, 'mipi_dsi_dcs_set_column_address', _get_params_int(2, 'big')
	SET_PAGE_ADDRESS = 0x2B, 4, 'mipi_dsi_dcs_set_page_address', _get_params_int(2, 'big')
	WRITE_MEMORY_START = 0x2C,
	WRITE_LUT = 0x2D,
	READ_MEMORY_START = 0x2E,
	SET_PARTIAL_ROWS = 0x30,
	SET_PARTIAL_COLUMNS = 0x31,
	SET_SCROLL_AREA = 0x33, 6,
	SET_TEAR_OFF = 0x34, 0, 'mipi_dsi_dcs_set_tear_off'
	SET_TEAR_ON = 0x35, 1, 'mipi_dsi_dcs_set_tear_on', TearMode.get_params
	SET_ADDRESS_MODE = 0x36, 1,
	SET_SCROLL_START = 0x37, 2,
	EXIT_IDLE_MODE = 0x38, 0,
	ENTER_IDLE_MODE = 0x39, 0,
	SET_PIXEL_FORMAT = 0x3A, 1, 'mipi_dsi_dcs_set_pixel_format'
	WRITE_MEMORY_CONTINUE = 0x3C,
	SET_3D_CONTROL = 0x3D,
	READ_MEMORY_CONTINUE = 0x3E,
	# GET_3D_CONTROL = 0x3F,
	SET_VSYNC_TIMING = 0x40
	SET_TEAR_SCANLINE = 0x44, 2, 'mipi_dsi_dcs_set_tear_scanline', _get_params_int(2, 'big')
	GET_SCANLINE = 0x45,
	SET_DISPLAY_BRIGHTNESS = 0x51, (1, 2), 'mipi_dsi_dcs_set_display_brightness', _get_params_int(2, 'little')
	# GET_DISPLAY_BRIGHTNESS = 0x52,
	WRITE_CONTROL_DISPLAY = 0x53, 1,
	# GET_CONTROL_DISPLAY = 0x54,
	WRITE_POWER_SAVE = 0x55, 1,
	# GET_POWER_SAVE = 0x56,
	SET_CABC_MIN_BRIGHTNESS = 0x5E,
	# GET_CABC_MIN_BRIGHTNESS = 0x5F,
	READ_DDB_START = 0xA1,
	READ_PPS_START = 0xA2,
	READ_DDB_CONTINUE = 0xA8,
	READ_PPS_CONTINUE = 0xA9,

	def __new__(cls, value: int, nargs: Union[int, Tuple[int]] = (), method: str = None,
				_get_params=_get_params_hex) -> DCSCommand:
		obj = object.__new__(cls)
		obj._value_ = value
		obj.nargs = nargs if isinstance(nargs, tuple) else (nargs,)
		obj.method = method
		obj._get_params = _get_params
		return obj

	@property
	def identifier(self):
		return 'MIPI_DCS_' + self.name

	@property
	def description(self):
		return self.name.lower().replace('_', ' ')

	def get_params(self, b: bytes):
		params = self._get_params(b)
		params.insert(0, 'dsi')
		return params

	@staticmethod
	def find(payload: bytes, dumb: bool) -> Optional[DCSCommand]:
		try:
			dcs = DCSCommand(payload[0])
		except ValueError:
			# Not a specified DCS command
			return None

		if dumb and dcs not in DCSCommand._DUMB_ALLOWED:
			return None

		if dcs.nargs and len(payload) - 1 not in dcs.nargs:
			# Argument count does not match. Weird.
			expected_args = " or ".join(str(i) for i in dcs.nargs)
			print(f"WARNING: DCS command {dcs.name} with incorrect argument count "
				  f"(expected: {expected_args}, is: {len(payload) - 1})")
			return None

		try:
			# Try to parse the argument(s)
			dcs.get_params(payload[1:])
		except ValueError as e:
			# Not a valid argument. Weird.
			print(f"WARNING: DCS command {dcs.name} with invalid arguments {payload[1:]}: {e}")
			return None

		return dcs


DCSCommand._DUMB_ALLOWED = [DCSCommand.ENTER_SLEEP_MODE, DCSCommand.EXIT_SLEEP_MODE,
							DCSCommand.SET_DISPLAY_ON, DCSCommand.SET_DISPLAY_OFF]


def _generate_checked_call(method: str, args: List[str], description: str) -> str:
	return f'''\
{wrap.join(f'	ret = {method}(', ',', ');', args)}
	if (ret < 0) {{
		dev_err(dev, "Failed to {description}: %d\\n", ret);
		return ret;
	}}\
'''


MACROS = {
	'dsi_generic_write_seq': 'mipi_dsi_generic_write',
	'dsi_dcs_write_seq': 'mipi_dsi_dcs_write_buffer',
}


def _generate_generic_write(t: Transaction, payload: bytes, options: Options) -> str:
	# TODO: Warn when downstream uses LONG_WRITE but mainline would use SHORT
	params = _get_params_hex(payload)
	params.insert(0, 'dsi')
	return wrap.join('\tdsi_generic_write_seq(', ',', ');', params, force=2)


def _generate_dcs_write(t: Transaction, payload: bytes, options: Options) -> str:
	# TODO: Warn when downstream uses LONG_WRITE but mainline would use SHORT

	dcs = DCSCommand.find(payload, options.dumb_dcs)
	if dcs and dcs.method:
		return _generate_checked_call(dcs.method, dcs.get_params(payload[1:]), dcs.description)

	params = _get_params_hex(payload)
	if dcs:
		params[0] = dcs.identifier
	params.insert(0, 'dsi')

	return wrap.join('\tdsi_dcs_write_seq(', ',', ');', params, force=2)


def _generate_peripheral(t: Transaction, payload: bytes, options: Options) -> str:
	if t == Transaction.TURN_ON_PERIPHERAL:
		return _generate_checked_call('mipi_dsi_turn_on_peripheral', ['dsi'], t.description)
	elif t == Transaction.SHUTDOWN_PERIPHERAL:
		return _generate_checked_call('mipi_dsi_shutdown_peripheral', ['dsi'], t.description)
	else:
		raise ValueError(t)


def _generate_null_packet(t: Transaction, payload: bytes, options: Options) -> str:
	return "\t// WARNING: Ignoring weird NULL_PACKET (dummy packet)"


def _generate_fallback(t: Transaction, payload: bytes, options: Options) -> str:
	raise ValueError(t.name + ' is not supported')


# MIPI DSI Processor-to-Peripheral transaction types
@unique
class Transaction(Enum):
	V_SYNC_START = 0x01,
	V_SYNC_END = 0x11,
	H_SYNC_START = 0x21,
	H_SYNC_END = 0x31,

	COLOR_MODE_OFF = 0x02,
	COLOR_MODE_ON = 0x12,
	SHUTDOWN_PERIPHERAL = 0x22, 0, _generate_peripheral
	TURN_ON_PERIPHERAL = 0x32, 0, _generate_peripheral

	GENERIC_SHORT_WRITE_0_PARAM = 0x03, 0, _generate_generic_write
	GENERIC_SHORT_WRITE_1_PARAM = 0x13, 1, _generate_generic_write
	GENERIC_SHORT_WRITE_2_PARAM = 0x23, 2, _generate_generic_write

	GENERIC_READ_REQUEST_0_PARAM = 0x04,
	GENERIC_READ_REQUEST_1_PARAM = 0x14,
	GENERIC_READ_REQUEST_2_PARAM = 0x24,

	DCS_SHORT_WRITE = 0x05, 0, _generate_dcs_write
	DCS_SHORT_WRITE_PARAM = 0x15, 1, _generate_dcs_write

	DCS_READ = 0x06,

	DCS_COMPRESSION_MODE = 0x07,
	PPS_LONG_WRITE = 0x0A,

	SET_MAXIMUM_RETURN_PACKET_SIZE = 0x37,

	END_OF_TRANSMISSION = 0x08,

	NULL_PACKET = 0x09, -1, _generate_null_packet
	BLANKING_PACKET = 0x19,
	GENERIC_LONG_WRITE = 0x29, -1, _generate_generic_write
	DCS_LONG_WRITE = 0x39, -1, _generate_dcs_write

	LOOSELY_PACKED_PIXEL_STREAM_YCBCR20 = 0x0c,
	PACKED_PIXEL_STREAM_YCBCR24 = 0x1c,
	PACKED_PIXEL_STREAM_YCBCR16 = 0x2c,

	PACKED_PIXEL_STREAM_30 = 0x0d,
	PACKED_PIXEL_STREAM_36 = 0x1d,
	PACKED_PIXEL_STREAM_YCBCR12 = 0x3d,

	PACKED_PIXEL_STREAM_16 = 0x0e,
	PACKED_PIXEL_STREAM_18 = 0x1e,
	PIXEL_STREAM_3BYTE_18 = 0x2e,
	PACKED_PIXEL_STREAM_24 = 0x3e,

	def __new__(cls, value: int, max_args: int = -1, generate=_generate_fallback) -> Transaction:
		obj = object.__new__(cls)
		obj._value_ = value
		obj.max_args = max_args
		obj._generate = generate
		return obj

	@property
	def identifier(self):
		return 'MIPI_DSI_' + self.name

	@property
	def description(self):
		return self.name.lower().replace('_', ' ')

	def generate(self, payload: bytes, options: Options) -> str:
		return self._generate(self, payload, options)
