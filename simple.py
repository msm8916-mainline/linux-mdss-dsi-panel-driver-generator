# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

from panel import Panel


def generate_panel_simple(p: Panel) -> None:
	with open(f'{p.id}/panel-simple-{p.id}.c', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) 2013, The Linux Foundation. All rights reserved.

static const struct drm_display_mode {p.id}_mode = {{
	.clock = ({p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp}) * ({p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp}) * {p.framerate} / 1000,
	.hdisplay = {p.h.px},
	.hsync_start = {p.h.px} + {p.h.fp},
	.hsync_end = {p.h.px} + {p.h.fp} + {p.h.pw},
	.htotal = {p.h.px} + {p.h.fp} + {p.h.pw} + {p.h.bp},
	.vdisplay = {p.v.px},
	.vsync_start = {p.v.px} + {p.v.fp},
	.vsync_end = {p.v.px} + {p.v.fp} + {p.v.pw},
	.vtotal = {p.v.px} + {p.v.fp} + {p.v.pw} + {p.v.bp},
	.vrefresh = {p.framerate},
}};

static const struct panel_desc_dsi {p.id} = {{
	.desc = {{
		.modes = &{p.id}_mode,
		.num_modes = 1,
		.bpc = {int(p.bpp / 3)},
		.size = {{
			.width = {p.h.size},
			.height = {p.v.size},
		}},
	}},
	.flags = {' | '.join(p.flags)},
	.format = MIPI_DSI_FMT_RGB888,
	.lanes = {p.lanes},
}};
''')
