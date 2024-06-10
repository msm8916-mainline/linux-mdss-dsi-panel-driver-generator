# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import datetime

import wrap
from panel import Panel, Mode, CommandSequence, LaneMap, TrafficMode


def generate_commands(p: Panel, cmd_name: str) -> str:
	cmd: CommandSequence = p.cmds[cmd_name]

	cmds = ""
	struct = f"static struct mipi_dsi_cmd {p.id}_{cmd_name}_command[] = {{\n"

	s = ""
	i = 0
	for c in cmd.seq:
		b = bytearray()
		long = c.type.is_long
		if long:
			b += int.to_bytes(len(c.payload), 2, 'little')  # Word count (WC)
		else:
			assert len(c.payload) <= 2, f"Payload too long: {len(c.payload)}"
			itr = iter(c.payload)
			b.append(next(itr, 0))
			b.append(next(itr, 0))

		b.append(c.type.value | c.vc << 6)
		b.append(int(c.ack) << 5 | int(long) << 6 | int(c.last) << 7)

		if long:
			b += bytes(c.payload)

			# DMA command size must be multiple of 4
			mod = len(b) % 4
			if mod != 0:
				b += bytes([0xff] * (4 - mod))

		name = f'{p.id}_{cmd_name}_cmd_{i}'
		cmds += f'static char {name}[] = {{\n'
		cmds += wrap.join('\t', ',', '', [f'{byte:#04x}' for byte in b], wrap=54)
		cmds += '\n};\n'

		struct += f'\t{{ sizeof({name}), {name}, {c.wait} }},\n'
		i += 1

	struct += '};'

	return cmds + '\n' + struct


def generate_cmd_info(p: Panel) -> str:
	s = f'static struct commandpanel_info {p.id}_command_panel = {{\n'
	if p.mode != Mode.CMD_MODE:
		return s + '\t/* Unused, this is a video mode panel */\n};'

	s += '\t/* FIXME: This is a command mode panel */\n'
	return s + '};'


def generate_video_info(p: Panel) -> str:
	s = f'static struct videopanel_info {p.id}_video_panel = {{\n'

	s += f'''\
	.hsync_pulse = {int('MIPI_DSI_MODE_VIDEO_HSE' in p.flags)},
	.hfp_power_mode = {int('MIPI_DSI_MODE_VIDEO_NO_HFP' in p.flags)},
	.hbp_power_mode = {int('MIPI_DSI_MODE_VIDEO_NO_HBP' in p.flags)},
	.hsa_power_mode = {int('MIPI_DSI_MODE_VIDEO_NO_HSA' in p.flags)},
	.bllp_eof_power_mode = {int(p.bllp_eof_power_mode)},
	.bllp_power_mode = {int(p.bllp_power_mode)},
	.traffic_mode = {list(TrafficMode.__members__.values()).index(p.traffic_mode)},
	/* This is bllp_eof_power_mode and bllp_power_mode combined */
	.bllp_eof_power = {int(p.bllp_eof_power_mode)} << 3 | {int(p.bllp_power_mode)} << 0,
'''
	return s + '};'


def generate_reset_seq(p: Panel) -> str:
	if not p.reset_seq:
		return ''

	return f'''
static struct panel_reset_sequence {p.id}_reset_seq = {{
	.pin_state = {{ {', '.join(str(res[0]) for res in p.reset_seq)} }},
	.sleep = {{ {', '.join(str(res[1]) for res in p.reset_seq)} }},
	.pin_direction = 2,
}};
'''


def generate_backlight(p: Panel) -> str:
	if not p.backlight:
		return ''

	return f'''
static struct backlight {p.id}_backlight = {{
	.bl_interface_type = BL_{p.backlight.name},
	.bl_min_level = 1,
	.bl_max_level = {p.max_brightness},
}};
'''


def generate_lk_driver(p: Panel) -> None:
	if 'sim' in p.id:
		return

	define = f'_PANEL_{p.id.upper()}_H_'

	with open(f'{p.id}/lk_panel_{p.id}.h', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) {datetime.date.today().year} FIXME
// Generated with linux-mdss-dsi-panel-driver-generator from vendor device tree:
//   Copyright (c) 2014, The Linux Foundation. All rights reserved. (FIXME)

#ifndef {define}
#define {define}

#include <mipi_dsi.h>
#include <panel_display.h>
#include <panel.h>
#include <string.h>

static struct panel_config {p.id}_panel_data = {{
	.panel_node_id = "{p.node_name}",
	.panel_controller = "dsi:0:",
	.panel_compatible = "qcom,mdss-dsi-panel",
	.panel_type = {int(p.mode == Mode.CMD_MODE)},
	.panel_destination = "DISPLAY_1",
	/* .panel_orientation not supported yet */
	.panel_framerate = {p.framerate},
	.panel_lp11_init = {int(p.lp11_init)},
	.panel_init_delay = {p.init_delay},
}};

static struct panel_resolution {p.id}_panel_res = {{
	.panel_width = {p.h.px},
	.panel_height = {p.v.px},
	.hfront_porch = {p.h.fp},
	.hback_porch = {p.h.bp},
	.hpulse_width = {p.h.pw},
	.hsync_skew = {p.hsync_skew},
	.vfront_porch = {p.v.fp},
	.vback_porch = {p.v.bp},
	.vpulse_width = {p.v.pw},
	/* Borders not supported yet */
}};

static struct color_info {p.id}_color = {{
	.color_format = {p.bpp},
	.color_order = DSI_RGB_SWAP_RGB,
	.underflow_color = 0xff,
	/* Borders and pixel packing not supported yet */
}};

{generate_commands(p, 'on')}

{generate_commands(p, 'off')}

static struct command_state {p.id}_state = {{
	.oncommand_state = {int(p.cmds['on'].state == CommandSequence.State.HS_MODE)},
	.offcommand_state = {int(p.cmds['off'].state == CommandSequence.State.HS_MODE)},
}};

{generate_cmd_info(p)}

{generate_video_info(p)}

static struct lane_configuration {p.id}_lane_config = {{
	.dsi_lanes = {p.lanes},
	.dsi_lanemap = {list(LaneMap.__members__.values()).index(p.lane_map)},
	.lane0_state = {int(p.lanes > 0)},
	.lane1_state = {int(p.lanes > 1)},
	.lane2_state = {int(p.lanes > 2)},
	.lane3_state = {int(p.lanes > 3)},
	.force_clk_lane_hs = {int('MIPI_DSI_CLOCK_NON_CONTINUOUS' not in p.flags)},
}};

static const uint32_t {p.id}_timings[] = {{
	{', '.join(f'{byte:#04x}' for byte in p.timings)}
}};

static struct panel_timing {p.id}_timing_info = {{
	.tclk_post = {p.tclk_post:#04x},
	.tclk_pre = {p.tclk_pre:#04x},
}};
{generate_reset_seq(p)}{generate_backlight(p)}
{wrap.join(f'static inline void panel_{p.id}_select(', ',', ')',
		   ['struct panel_struct *panel', 'struct msm_panel_info *pinfo',
			'struct mdss_dsi_phy_ctrl *phy_db'])}
{{
	panel->paneldata = &{p.id}_panel_data;
	panel->panelres = &{p.id}_panel_res;
	panel->color = &{p.id}_color;
	panel->videopanel = &{p.id}_video_panel;
	panel->commandpanel = &{p.id}_command_panel;
	panel->state = &{p.id}_state;
	panel->laneconfig = &{p.id}_lane_config;
	panel->paneltiminginfo = &{p.id}_timing_info;
	panel->panelresetseq = {f'&{p.id}_reset_seq' if p.reset_seq else 'NULL'};
	panel->backlightinfo = {f'&{p.id}_backlight' if p.backlight else 'NULL'};
	pinfo->mipi.panel_on_cmds = {p.id}_on_command;
	pinfo->mipi.num_of_panel_on_cmds = ARRAY_SIZE({p.id}_on_command);
	memcpy(phy_db->timing, {p.id}_timings, TIMING_SIZE);
	phy_db->regulator_mode = {'DSI_PHY_REGULATOR_LDO_MODE' if p.ldo_mode else 'DSI_PHY_REGULATOR_DCDC_MODE'};
}}

#endif /* {define} */
''')
