# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import wrap
from panel import Panel


def generate_mode(p: Panel) -> str:
	return f'''\
static const struct drm_display_mode {p.short_id}_mode = {{
	.clock = ({p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp}) * ({p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp}) * {p.framerate} / 1000,
	.hdisplay = {p.h.px},
	.hsync_start = {p.h.px} + {p.h.fp},
	.hsync_end = {p.h.px} + {p.h.fp} + {p.h.pw},
	.htotal = {p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp},
	.vdisplay = {p.v.px},
	.vsync_start = {p.v.px} + {p.v.fp},
	.vsync_end = {p.v.px} + {p.v.fp} + {p.v.pw},
	.vtotal = {p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp},
	.width_mm = {p.h.size},
	.height_mm = {p.v.size},
}};
'''

def generate_mode_common(p: Panel) -> str:
	return f'''\
	.mode = {{
		.clock = ({p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp}) * ({p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp}) * {p.framerate} / 1000,
		.hdisplay = {p.h.px},
		.hsync_start = {p.h.px} + {p.h.fp},
		.hsync_end = {p.h.px} + {p.h.fp} + {p.h.pw},
		.htotal = {p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp},
		.vdisplay = {p.v.px},
		.vsync_start = {p.v.px} + {p.v.fp},
		.vsync_end = {p.v.px} + {p.v.fp} + {p.v.pw},
		.vtotal = {p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp},
		.width_mm = {p.h.size},
		.height_mm = {p.v.size},
	}},'''

def generate_panel_simple(p: Panel) -> None:
	name = p.short_id.replace('_', '-')
	with open(f'{p.id}/panel-simple-{name}.c', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) 2013, The Linux Foundation. All rights reserved.

{generate_mode(p)}
static const struct panel_desc_dsi {p.short_id} = {{
	.desc = {{
		.modes = &{p.short_id}_mode,
		.num_modes = 1,
		.bpc = {int(p.bpp / 3)},
		.size = {{
			.width = {p.h.size},
			.height = {p.v.size},
		}},
		.connector_type = DRM_MODE_CONNECTOR_DSI,
	}},
{wrap.join('	.flags = ', ' |', ',', p.flags)}
	.format = {p.format},
	.lanes = {p.lanes},
}};
''')
