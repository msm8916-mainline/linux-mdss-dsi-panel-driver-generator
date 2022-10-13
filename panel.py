# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import Enum, unique
from typing import Iterator, List, Optional

import libfdt

import mipi
from fdt2 import Fdt2


@unique
class Mode(Enum):
	VIDEO_MODE = 'dsi_video_mode', ['MIPI_DSI_MODE_VIDEO']
	CMD_MODE = 'dsi_cmd_mode', []

	def __new__(cls, value: str, flags: List[str]) -> Mode:
		obj = object.__new__(cls)
		obj._value_ = value
		obj.flags = flags
		return obj


@unique
class TrafficMode(Enum):
	SYNC_PULSE = 'non_burst_sync_pulse', ['MIPI_DSI_MODE_VIDEO_SYNC_PULSE']
	SYNC_EVENT = 'non_burst_sync_event', []
	BURST_MODE = 'burst_mode', ['MIPI_DSI_MODE_VIDEO_BURST']

	def __new__(cls, value: str, flags: List[str]) -> TrafficMode:
		obj = object.__new__(cls)
		obj._value_ = value
		obj.flags = flags
		return obj

	@staticmethod
	def parse(prop: libfdt.Property) -> Optional[TrafficMode]:
		if prop.is_str():
			return TrafficMode(prop.as_str())

		print(f"WARNING: qcom,mdss-dsi-traffic-mode is not a null terminated string:", prop)

		# Some Samsung panels have the traffic mode as index for some reason
		if len(prop) == 4:
			i = prop.as_uint32()
			traffic_modes = list(TrafficMode.__members__.values())
			if i < len(traffic_modes):
				print(f"Interpreting qcom,mdss-dsi-traffic-mode as numeric index: {i} == {traffic_modes[i]}")
				return traffic_modes[i]

		# Use the default in mdss_dsi_panel.c
		print("Falling back to MIPI_DSI_MODE_VIDEO_SYNC_PULSE")
		return TrafficMode.SYNC_PULSE


@unique
class LaneMap(Enum):
	MAP_0123 = [0, 1, 2, 3]
	MAP_3012 = [3, 0, 1, 2]
	MAP_2301 = [2, 3, 0, 1]
	MAP_1230 = [1, 2, 3, 0]
	MAP_0321 = [0, 3, 2, 1]
	MAP_1032 = [1, 0, 3, 2]
	MAP_2103 = [2, 1, 0, 3]
	MAP_3210 = [3, 2, 1, 0]

	def __new__(cls, log2phys: List[int]) -> LaneMap:
		obj = object.__new__(cls)
		obj._value_ = "lane_map_" + ''.join(map(str, log2phys))
		# Logical lane -> physical lane (used in downstream)
		obj.log2phys = log2phys
		# Physical lane -> logical lane (used in mainline)
		obj.phys2log = [0, 0, 0, 0]
		for i, n in enumerate(log2phys):
			obj.phys2log[n] = i
		return obj

	@staticmethod
	def parse(prop: Optional[libfdt.Property]) -> LaneMap:
		if not prop:
			return LaneMap.MAP_0123
		if prop.is_str():  # Null terminated string
			return LaneMap(prop.as_str())

		print(f"WARNING: qcom,mdss-dsi-lane-map is not a null terminated string:", prop)
		return LaneMap.MAP_0123


@unique
class BacklightControl(Enum):
	PWM = 'bl_ctrl_pwm'
	DCS = 'bl_ctrl_dcs'
	WLED = 'bl_ctrl_wled'
	SAMSUNG_PWM = 'bl_ctrl_ss_pwm'


class Dimension:
	@unique
	class Type(Enum):
		HORIZONTAL = 'h', 'width'
		VERTICAL = 'v', 'height'

		def __init__(self, prefix: str, size: str) -> None:
			self.prefix = prefix
			self.size = size

	def __init__(self, fdt: Fdt2, panel_node: int, mode_node: int, t: Type) -> None:
		self.type = type
		self.px = fdt.getprop(mode_node, f'qcom,mdss-dsi-panel-{t.size}').as_uint32()
		self.fp = fdt.getprop(mode_node, f'qcom,mdss-dsi-{t.prefix}-front-porch').as_uint32()
		self.bp = fdt.getprop(mode_node, f'qcom,mdss-dsi-{t.prefix}-back-porch').as_uint32()
		self.pw = fdt.getprop(mode_node, f'qcom,mdss-dsi-{t.prefix}-pulse-width').as_uint32()
		self.size = fdt.getprop_uint32(panel_node, f'qcom,mdss-pan-physical-{t.size}-dimension')


@dataclass
class Command:
	type: mipi.Transaction
	last: bool
	vc: int
	ack: bool
	wait: int
	payload: bytes
	generated: str = None


class CommandSequence:
	generated: str = ''

	@unique
	class State(Enum):
		LP_MODE = 'dsi_lp_mode'
		HS_MODE = 'dsi_hs_mode'

	def __init__(self, fdt: Fdt2, node: int, cmd: str) -> None:
		self.state = CommandSequence.State(fdt.getprop(node, f'qcom,mdss-dsi-{cmd}-command-state').as_str())
		self.seq = []

		prop = fdt.getprop_or_none(node, f'qcom,mdss-dsi-{cmd}-command')
		if prop is None:
			print(f'Warning: qcom,mdss-dsi-{cmd}-command does not exist')
			return  # No commands
		itr = iter(prop)

		if cmd == 'on':
			# WHY SONY/LG, WHY?????? Just put it in on-command...
			init = fdt.getprop_or_none(node, 'somc,mdss-dsi-init-command')
			if init:
				itr = itertools.chain(init, itr)

			on = fdt.getprop_or_none(node, 'lge,display-on-cmds')
			if on:
				itr = itertools.chain(itr, on)

		for dtype in itr:
			last, vc, ack, wait = next(itr), next(itr), next(itr), next(itr)
			dlen = next(itr) << 8 | next(itr)
			payload = bytes(next(itr) for _ in range(0, dlen))

			t = mipi.Transaction(dtype)

			# Very often there are too many arguments encoded in the command stream.
			# These are redundant, because they would be never sent anyway.
			max_dlen = t.max_args + 1
			if 0 < max_dlen < dlen:
				payload = payload[:max_dlen]

			self.seq.append(Command(t, last, vc, ack, wait, payload))


def _remove_prefixes(text: str, *args: str) -> str:
	for prefix in args:
		text = text[len(prefix):] if text.startswith(prefix) else text
	return text


def _replace_all(text: str, *args: str) -> str:
	for replace in args:
		text = text.replace(replace, '')
	return text


def _remove_before(text: str, sub: str) -> str:
	i = text.find(sub)
	return text[i + 1:] if i >= 0 else text


def _find_mode_node(fdt: Fdt2, node: int) -> int:
	timings_node = fdt.subnode_or_none(node, "qcom,mdss-dsi-display-timings")
	if timings_node is None:
		return node

	mode_node = None
	for timing in fdt.subnodes(timings_node):
		if mode_node:
			print("WARNING: Multiple display timings are not supported yet, using first!")
			break
		mode_node = timing

	assert mode_node, "No display timings found"
	return mode_node


class Panel:
	def __init__(self, name: str, fdt: Fdt2, node: int) -> None:
		self.name = name
		self.node_name = fdt.get_name(node)
		self.id = _remove_before(_remove_prefixes(self.node_name, 'qcom,mdss_dsi_', 'ss_dsi_panel_', 'mot_').lower(), ',')
		print(f'Parsing: {self.id} ({name})')
		self.short_id = _replace_all(self.id, '_panel', '_video', '_vid', '_cmd',
									 '_fhd', '_hd', '_qhd', '_720p', '_1080p',
									 '_wvga', '_fwvga', '_qvga', '_xga', '_wxga')

		# Newer SoCs can use panels in different modes (resolution, refresh rate etc).
		# We don't support this properly yet but many panels just have a single mode
		# ("timing") defined, so let's try to support this here.
		mode_node = _find_mode_node(fdt, node)
		self.h = Dimension(fdt, node, mode_node, Dimension.Type.HORIZONTAL)
		self.v = Dimension(fdt, node, mode_node, Dimension.Type.VERTICAL)
		self.framerate = fdt.getprop(mode_node, 'qcom,mdss-dsi-panel-framerate').as_uint32()
		self.bpp = fdt.getprop(node, 'qcom,mdss-dsi-bpp').as_uint32()
		self.mode = Mode(fdt.getprop(node, 'qcom,mdss-dsi-panel-type').as_str())
		self.traffic_mode = TrafficMode.parse(fdt.getprop(node, 'qcom,mdss-dsi-traffic-mode'))

		backlight = fdt.getprop_or_none(node, 'qcom,mdss-dsi-bl-pmic-control-type')
		self.backlight = BacklightControl(backlight.as_str()) if backlight else None
		self.max_brightness = fdt.getprop_uint32(node, 'qcom,mdss-dsi-bl-max-level', None)
		if self.backlight == BacklightControl.DCS and self.max_brightness is None:
			print("WARNING: DCS backlight without maximum brightness, ignoring...")
			self.backlight = None

		self.lanes = 0
		while fdt.getprop_or_none(node, f'qcom,mdss-dsi-lane-{self.lanes}-state') is not None:
			self.lanes += 1
		self.lane_map = LaneMap.parse(fdt.getprop_or_none(node, 'qcom,mdss-dsi-lane-map'))

		self.flags = self.mode.flags + self.traffic_mode.flags

		if fdt.getprop_uint32(node, 'qcom,mdss-dsi-h-sync-pulse') != 0:
			self.flags.append('MIPI_DSI_MODE_VIDEO_HSE')

		if fdt.getprop_or_none(node, 'qcom,mdss-dsi-tx-eot-append') is None:
			self.flags.append('MIPI_DSI_MODE_NO_EOT_PACKET')

		if fdt.getprop_or_none(node, 'qcom,mdss-dsi-force-clock-lane-hs') is None \
				and fdt.getprop_or_none(node, 'qcom,mdss-dsi-force-clk-lane-hs') is None \
				and fdt.getprop_uint32(node, 'qcom,mdss-force-clk-lane-hs', ignore_empty=True) == 0:
			self.flags.append('MIPI_DSI_CLOCK_NON_CONTINUOUS')

		if fdt.getprop_or_none(node, 'qcom,mdss-dsi-hfp-power-mode') is not None:
			self.flags.append('MIPI_DSI_MODE_VIDEO_NO_HFP')
		if fdt.getprop_or_none(node, 'qcom,mdss-dsi-hbp-power-mode') is not None:
			self.flags.append('MIPI_DSI_MODE_VIDEO_NO_HBP')
		if fdt.getprop_or_none(node, 'qcom,mdss-dsi-hsa-power-mode') is not None:
			self.flags.append('MIPI_DSI_MODE_VIDEO_NO_HSA')

		reset_seq = fdt.getprop_or_none(node, 'qcom,mdss-dsi-reset-sequence')
		if reset_seq is not None:
			itr = iter(reset_seq.as_uint32_array())
			self.reset_seq = list(zip(itr, itr))
		else:
			self.reset_seq = None

		self.cmds = {
			'on': CommandSequence(fdt, mode_node, 'on'),
			'off': CommandSequence(fdt, mode_node, 'off')
		}

		# If all commands are sent in LPM, add flag globally
		if self.cmds['on'].state == CommandSequence.State.LP_MODE == self.cmds['off'].state:
			self.flags.append('MIPI_DSI_MODE_LPM')

		if self.bpp == 24:
			self.format = 'MIPI_DSI_FMT_RGB888'
		else:
			raise ValueError(f'Unsupported bpp: {self.bpp} (TODO)')

		# Sony </3
		prop = fdt.getprop_or_none(node, 'somc,mdss-phy-size-mm')
		if prop:
			phy_size_mm = prop.as_uint32_array()
			self.h.size = phy_size_mm[0]
			self.v.size = phy_size_mm[1]

		# Check dsi phy type
		self.cphy_mode = fdt.getprop_or_none(node, 'qcom,panel-cphy-mode') is not None

		# Check DSI controller if LDO mode is needed
		self.ldo_mode = False
		dsi_ctrl = fdt.getprop_or_none(node, 'qcom,mdss-dsi-panel-controller')
		if dsi_ctrl is not None:
			dsi_ctrl = fdt.node_offset_by_phandle(dsi_ctrl.as_uint32())
			self.ldo_mode = fdt.getprop_or_none(dsi_ctrl, 'qcom,regulator-ldo-mode') is not None

		# Timings are usually calculated by the driver except for downstream and LK
		p = fdt.getprop_or_none(node, 'qcom,mdss-dsi-panel-timings')
		self.timings = bytes(p) if p else bytes()
		self.tclk_post = fdt.getprop_uint32(node, 'qcom,mdss-dsi-t-clk-post')
		self.tclk_pre = fdt.getprop_uint32(node, 'qcom,mdss-dsi-t-clk-pre')

		# Additional weird values used by downstream and LK
		self.hsync_skew = fdt.getprop_uint32(node, 'qcom,mdss-dsi-h-sync-skew')
		self.bllp_power_mode = fdt.getprop_or_none(node, 'qcom,mdss-dsi-bllp-power-mode') is not None
		self.bllp_eof_power_mode = fdt.getprop_or_none(node, 'qcom,mdss-dsi-bllp-eof-power-mode') is not None
		self.lp11_init = fdt.getprop_or_none(node, 'qcom,mdss-dsi-lp11-init') is not None
		self.init_delay = fdt.getprop_uint32(node, 'qcom,mdss-dsi-init-delay-us')

		# Display Stream Compression
		self.compression_mode = fdt.getprop_or_none(mode_node, 'qcom,compression-mode')
		self.has_dsc = self.compression_mode is not None and self.compression_mode.as_str() == "dsc"

		if self.has_dsc:
			#self.dsc_lm_split = fdt.getprop_or_none(mode_node, 'qcom,lm-split')
			dsc_encoders = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-encoders')
			self.dsc_encoders = dsc_encoders.as_int32() if dsc_encoders else None

			dsc_slice_height = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-slice-height')
			self.dsc_slice_height = dsc_slice_height.as_int32() if dsc_slice_height else None

			dsc_slice_width = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-slice-width')
			self.dsc_slice_width = dsc_slice_width.as_int32() if dsc_slice_width else None

			dsc_slice_per_pkt = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-slice-per-pkt')
			self.dsc_slice_per_pkt = dsc_slice_per_pkt.as_int32() if dsc_slice_per_pkt else None

			dsc_bit_per_component = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-bit-per-component')
			self.dsc_bit_per_component = dsc_bit_per_component.as_int32() if dsc_bit_per_component else None

			dsc_bit_per_pixel = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-bit-per-pixel')
			self.dsc_bit_per_pixel = dsc_bit_per_pixel.as_int32() if dsc_bit_per_pixel else None

			self.dsc_dsc_block_prediction = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-block-prediction-enable') is not None

			dsc_version = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-version')
			self.dsc_version = dsc_version.as_int32() if dsc_version else 1

			dsc_scr_version = fdt.getprop_or_none(mode_node, 'qcom,mdss-dsc-scr-version')
			self.dsc_scr_version = dsc_scr_version.as_int32() if dsc_scr_version else 1

	@staticmethod
	def parse(fdt: Fdt2, node: int) -> Panel:
		name = fdt.getprop_or_none(node, 'qcom,mdss-dsi-panel-name')
		return name and Panel(name.as_str(), fdt, node)

	@staticmethod
	def find(fdt: Fdt2) -> Iterator[int]:
		for compatible in ['qcom,mdss_mdp', 'qcom,mdss_mdp3', 'qcom,sde-kms']:
			for mdp in fdt.find_by_compatible(compatible):
				for sub in fdt.subnodes(mdp):
					yield sub

		# Newer device trees do not necessarily have panels below MDP,
		# search for qcom,dsi-display node instead
		panel_phandles = set()

		for display in fdt.find_by_compatible('qcom,dsi-display'):
			# On even newer SoCs there is another node with qcom,dsi-display-list
			displays = fdt.getprop_or_none(display, 'qcom,dsi-display-list')
			if displays is None:
				dsi_panel = fdt.getprop_or_none(display, 'qcom,dsi-panel')
				if dsi_panel is not None:
					panel_phandles.add(dsi_panel.as_uint32())
			else:
				for display_phandle in displays.as_uint32_array():
					display = fdt.node_offset_by_phandle(display_phandle)
					panel_phandles.add(fdt.getprop(display, 'qcom,dsi-panel').as_uint32())

		for phandle in panel_phandles:
			yield fdt.node_offset_by_phandle(phandle)
