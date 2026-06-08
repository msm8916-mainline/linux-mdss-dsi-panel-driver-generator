# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import wrap
from panel import Dimension, Panel


def _mode_fields(h: Dimension, v: Dimension, framerate: int, indent: str) -> str:
	return f'''\
{indent}.clock = ({h.px} + {h.fp} + {h.pw} + {h.bp}) * ({v.px} + {v.fp} + {v.pw} + {v.bp}) * {framerate} / 1000,
{indent}.hdisplay = {h.px},
{indent}.hsync_start = {h.px} + {h.fp},
{indent}.hsync_end = {h.px} + {h.fp} + {h.pw},
{indent}.htotal = {h.px} + {h.fp} + {h.pw} + {h.bp},
{indent}.vdisplay = {v.px},
{indent}.vsync_start = {v.px} + {v.fp},
{indent}.vsync_end = {v.px} + {v.fp} + {v.pw},
{indent}.vtotal = {v.px} + {v.fp} + {v.pw} + {v.bp},
{indent}.width_mm = {h.size},
{indent}.height_mm = {v.size},
{indent}.type = DRM_MODE_TYPE_DRIVER,'''


def generate_mode(p: Panel) -> str:
	if not p.extra_timings:
		return f'''\
static const struct drm_display_mode {p.short_id}_mode = {{
{_mode_fields(p.h, p.v, p.framerate, '\t')}
}};
'''

	s = f'static const struct drm_display_mode {p.short_id}_modes[] = {{\n'
	for h, v, fr in [(p.h, p.v, p.framerate)] + [(t.h, t.v, t.framerate) for t in p.extra_timings]:
		s += f'\t{{ /* {h.px}x{v.px} @ {fr}Hz */\n'
		s += _mode_fields(h, v, fr, '\t\t')
		s += '\n\t},\n'
	s += '};\n'
	return s


def generate_panel_simple(p: Panel) -> None:
	name = p.short_id.replace('_', '-')
	mode_ref = f'&{p.short_id}_mode' if not p.extra_timings else f'{p.short_id}_modes'
	num_modes = 1 if not p.extra_timings else f'ARRAY_SIZE({p.short_id}_modes)'
	with open(f'{p.id}/panel-simple-{name}.c', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) 2013, The Linux Foundation. All rights reserved.

{generate_mode(p)}
static const struct panel_desc_dsi {p.short_id} = {{
	.desc = {{
		.modes = {mode_ref},
		.num_modes = {num_modes},
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
