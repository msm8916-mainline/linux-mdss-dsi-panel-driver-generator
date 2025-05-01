# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import datetime

import mipi
import simple
import wrap
from generator import Options, GpioFlag
from panel import Panel, BacklightControl, CommandSequence, CompressionMode


def generate_includes(p: Panel, options: Options) -> str:
	includes = {
		'linux': {
			'module.h',
			'mod_devicetable.h',
			'delay.h',
		},
		'video': set(),
		'drm': {
			'drm_mipi_dsi.h',
			'drm_modes.h',
			'drm_panel.h',
			'drm_probe_helper.h',
		},
	}

	if p.reset_seq:
		includes['linux'].add('gpio/consumer.h')
	if options.regulator:
		includes['linux'].add('regulator/consumer.h')
	if p.backlight == BacklightControl.DCS or options.backlight_fallback_dcs:
		includes['linux'].add('backlight.h')
	if p.compression_mode == CompressionMode.DSC:
		includes['drm'].add('display/drm_dsc.h')
		includes['drm'].add('display/drm_dsc_helper.h')

	for cmd in p.cmds.values():
		if 'MIPI_DCS_' in cmd.generated:
			includes['video'].add('mipi_display.h')
			break

	lines = []
	for group, headers in includes.items():
		if not headers:
			continue

		lines.append('')
		for header in sorted(headers):
			lines.append(f'#include <{group}/{header}>')

	return '\n'.join(lines)


def generate_struct(p: Panel, options: Options) -> str:
	variables = [
		'struct drm_panel panel',
		'struct mipi_dsi_device *dsi',
	]

	if p.compression_mode == CompressionMode.DSC:
		variables.append('struct drm_dsc_config dsc')

	if options.regulator:
		if len(options.regulator) > 1:
			variables.append(f'struct regulator_bulk_data *supplies')
		else:
			variables.append('struct regulator *supply')
	variables += [f'struct gpio_desc *{name}_gpio' for name in options.gpios.keys()]

	s = f'struct {p.short_id} {{'
	for v in variables:
		s += '\n'
		if v:
			s += '\t' + v + ';'
	s += '\n};'
	return s


def generate_regulator_bulk(p: Panel, options: Options) -> str:
	if not options.regulator or len(options.regulator) == 1:
		return ''

	s = '\n\n'
	s += f'static const struct regulator_bulk_data {p.short_id}_supplies[] = {{'
	for r in options.regulator:
		s += f'\n\t{{ .supply = "{r}" }},'
	s += '\n};'
	return s


# msleep(< 20) will possibly sleep up to 20ms
# In this case, usleep_range should be used
def msleep(m: int) -> str:
	if m >= 20:
		return f"msleep({m})"
	else:
		# It's hard to say what a good range would be...
		# Downstream uses usleep_range(m * 1000, m * 1000) but that doesn't quite sound great
		# Sleep for up to 1ms longer for now
		u = m * 1000
		return f"usleep_range({u}, {u + 1000})"


# msleep(< 20) will possibly sleep up to 20ms
# In this case, usleep_range should be used
def dsi_msleep(m: int) -> str:
	if m >= 20:
		return f"mipi_dsi_msleep(&dsi_ctx, {m})"
	else:
		# It's hard to say what a good range would be...
		# Downstream uses usleep_range(m * 1000, m * 1000) but that doesn't quite sound great
		# Sleep for up to 1ms longer for now
		u = m * 1000
		return f"mipi_dsi_usleep_range(&dsi_ctx, {u}, {u + 1000})"


def generate_reset(p: Panel, options: Options) -> str:
	if not p.reset_seq:
		return ''

	s = f'\nstatic void {p.short_id}_reset(struct {p.short_id} *ctx)\n{{\n'
	for state, sleep in p.reset_seq:
		# Invert reset sequence if GPIO is active low
		if options.gpios["reset"] & GpioFlag.ACTIVE_LOW:
			state = int(not bool(state))
		s += f'\tgpiod_set_value_cansleep(ctx->reset_gpio, {state});\n'
		if sleep:
			s += f'\t{msleep(sleep)};\n'
	s += '}\n'

	return s


def generate_commands(p: Panel, options: Options, cmd_name: str) -> str:
	cmd = p.cmds[cmd_name]

	s = f'''\
static int {p.short_id}_{cmd_name}(struct {p.short_id} *ctx)
{{
	struct mipi_dsi_multi_context dsi_ctx = {{ .dsi = ctx->dsi }};
'''

	if p.cmds['on'].state != p.cmds['off'].state:
		if cmd.state == CommandSequence.State.LP_MODE:
			s += '\n\tctx->dsi->mode_flags |= MIPI_DSI_MODE_LPM;\n'
		elif cmd.state == CommandSequence.State.HS_MODE:
			s += '\n\tctx->dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;\n'

	block = True
	for c in cmd.seq:
		if block or '{' in c.generated:
			s += '\n'
		block = '{' in c.generated

		s += c.generated + '\n'
		if c.wait and c.wait > options.ignore_wait:
			s += f'\t{dsi_msleep(c.wait)};\n'

	s += '''
	return dsi_ctx.accum_err;
}
'''
	return s


def generate_cleanup(p: Panel, options: Options, indent: int = 1) -> str:
	cleanup = []
	if p.reset_seq:
		cleanup.append('gpiod_set_value_cansleep(ctx->reset_gpio, 1);')
	if options.regulator:
		if len(options.regulator) > 1:
			cleanup.append(f'regulator_bulk_disable(ARRAY_SIZE({p.short_id}_supplies), ctx->supplies);')
		else:
			cleanup.append('regulator_disable(ctx->supply);')

	if cleanup:
		sep = '\n' + '\t' * indent
		return sep + sep.join(cleanup)
	else:
		return ''


def generate_prepare(p: Panel, options: Options) -> str:
	s = f'''\
static int {p.short_id}_prepare(struct drm_panel *panel)
{{
	struct {p.short_id} *ctx = to_{p.short_id}(panel);
	struct device *dev = &ctx->dsi->dev;
'''

	if p.compression_mode == CompressionMode.DSC:
		s += '''\
	struct drm_dsc_picture_parameter_set pps;
'''

	s += f'''\
	int ret;
'''

	if options.regulator:
		if len(options.regulator) > 1:
			s += f'''
	ret = regulator_bulk_enable(ARRAY_SIZE({p.short_id}_supplies), ctx->supplies);
	if (ret < 0) {{
		dev_err(dev, "Failed to enable regulators: %d\\n", ret);
		return ret;
	}}
'''
		else:
			s += '''
	ret = regulator_enable(ctx->supply);
	if (ret < 0) {
		dev_err(dev, "Failed to enable regulator: %d\\n", ret);
		return ret;
	}
'''

	if p.reset_seq:
		s += f'\n\t{p.short_id}_reset(ctx);\n'

	s += f'''
	ret = {p.short_id}_on(ctx);
	if (ret < 0) {{
		dev_err(dev, "Failed to initialize panel: %d\\n", ret);{generate_cleanup(p, options, 2)}
		return ret;
	}}
'''

	if p.compression_mode == CompressionMode.DSC:
		s += '''
	drm_dsc_pps_payload_pack(&pps, &ctx->dsc);

	ret = mipi_dsi_picture_parameter_set(ctx->dsi, &pps);
	if (ret < 0) {
		dev_err(panel->dev, "failed to transmit PPS: %d\\n", ret);
		return ret;
	}

	ret = mipi_dsi_compression_mode(ctx->dsi, true);
	if (ret < 0) {
		dev_err(dev, "failed to enable compression mode: %d\\n", ret);
		return ret;
	}

	msleep(28); /* TODO: Is this panel-dependent? */
'''

	s += '''
	return 0;
}
'''
	return s


def generate_unprepare(p: Panel, options: Options) -> str:
	return f'''\
static int {p.short_id}_unprepare(struct drm_panel *panel)
{{
	struct {p.short_id} *ctx = to_{p.short_id}(panel);
	struct device *dev = &ctx->dsi->dev;
	int ret;

	ret = {p.short_id}_off(ctx);
	if (ret < 0)
		dev_err(dev, "Failed to un-initialize panel: %d\\n", ret);
{generate_cleanup(p, options)}

	return 0;
}}
'''


def generate_backlight(p: Panel, options: Options) -> str:
	if p.backlight != BacklightControl.DCS and not options.backlight_fallback_dcs:
		return ''

	brightness_mask = ' & 0xff'
	if p.max_brightness > 255:
		brightness_mask = ''

	brightness_variant = ''
	if p.max_brightness > 255:
		brightness_variant = '_large'

	s = f'''\
static int {p.short_id}_bl_update_status(struct backlight_device *bl)
{{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
'''
	if options.backlight_gpio:
		s += f'\tstruct {p.short_id} *ctx = mipi_dsi_get_drvdata(dsi);\n'

	s += '''\
	u16 brightness = backlight_get_brightness(bl);
	int ret;
'''

	if options.backlight_gpio:
		s += '''
	gpiod_set_value_cansleep(ctx->backlight_gpio, !!brightness);
'''

	s += f'''
	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_set_display_brightness{brightness_variant}(dsi, brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return 0;
}}
'''

	if options.dcs_get_brightness:
		s += f'''
// TODO: Check if /sys/class/backlight/.../actual_brightness actually returns
// correct values. If not, remove this function.
static int {p.short_id}_bl_get_brightness(struct backlight_device *bl)
{{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
	u16 brightness;
	int ret;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_get_display_brightness{brightness_variant}(dsi, &brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return brightness{brightness_mask};
}}
'''
		get_brightness = f'\n\t.get_brightness = {p.short_id}_bl_get_brightness,'
	else:
		get_brightness = ''

	s += f'''
static const struct backlight_ops {p.short_id}_bl_ops = {{
	.update_status = {p.short_id}_bl_update_status,{get_brightness}
}};
'''
	s += f'''
static struct backlight_device *
{p.short_id}_create_backlight(struct mipi_dsi_device *dsi)
{{
	struct device *dev = &dsi->dev;
	const struct backlight_properties props = {{
		.type = BACKLIGHT_RAW,
		.brightness = {p.max_brightness or 255},
		.max_brightness = {p.max_brightness or 255},
	}};

	return devm_backlight_device_register(dev, dev_name(dev), dev, dsi,
					      &{p.short_id}_bl_ops, &props);
}}

'''
	return s


def generate_probe(p: Panel, options: Options) -> str:
	s = f'''\
static int {p.short_id}_probe(struct mipi_dsi_device *dsi)
{{
	struct device *dev = &dsi->dev;
	struct {p.short_id} *ctx;
'''

	s += f'''\
	int ret;

	ctx = devm_drm_panel_alloc(dev, struct {p.short_id}, panel,
				   &{p.short_id}_panel_funcs,
				   DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
'''

	if options.regulator:
		if len(options.regulator) > 1:
			s += f'''
	ret = devm_regulator_bulk_get_const(dev,
					    ARRAY_SIZE({p.short_id}_supplies),
					    {p.short_id}_supplies,
					    &ctx->supplies);
	if (ret < 0)
		return ret;
'''
		else:
			s += f'''
	ctx->supply = devm_regulator_get(dev, "{options.regulator[0]}");
	if (IS_ERR(ctx->supply))
		return dev_err_probe(dev, PTR_ERR(ctx->supply),
				     "Failed to get {options.regulator[0]} regulator\\n");
'''

	for name, flags in options.gpios.items():
		# TODO: In the future, we might want to change this to keep panel alive
		init = "GPIOD_OUT_LOW"
		if name == "reset":
			init = "GPIOD_OUT_HIGH"

		s += f'''
	ctx->{name}_gpio = devm_gpiod_get(dev, "{name}", {init});
	if (IS_ERR(ctx->{name}_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->{name}_gpio),
				     "Failed to get {name}-gpios\\n");
'''

	s += f'''
	ctx->dsi = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);

	dsi->lanes = {p.lanes};
	dsi->format = {p.format};
{wrap.join('	dsi->mode_flags = ', ' |', ';', p.flags)}

	ctx->panel.prepare_prev_first = true;
'''

	if options.backlight_fallback_dcs:
		s += f'''
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to get backlight\\n");

	/* Fallback to DCS backlight if no backlight is defined in DT */
	if (!ctx->panel.backlight) {{
		ctx->panel.backlight = {p.short_id}_create_backlight(dsi);
		if (IS_ERR(ctx->panel.backlight))
			return dev_err_probe(dev, PTR_ERR(ctx->panel.backlight),
					     "Failed to create backlight\\n");
	}}
'''
	elif p.backlight == BacklightControl.DCS:
		s += f'''
	ctx->panel.backlight = {p.short_id}_create_backlight(dsi);
	if (IS_ERR(ctx->panel.backlight))
		return dev_err_probe(dev, PTR_ERR(ctx->panel.backlight),
				     "Failed to create backlight\\n");
'''
	elif p.backlight:
		s += '''
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to get backlight\\n");
'''

	s += '''
	drm_panel_add(&ctx->panel);
'''

	if p.compression_mode == CompressionMode.DSC:
		s += f'''
	/* This panel only supports DSC; unconditionally enable it */
	dsi->dsc = &ctx->dsc;

	ctx->dsc.dsc_version_major = {(p.dsc_version >> 4) & 0xf};
	ctx->dsc.dsc_version_minor = {p.dsc_version & 0xf};

	/* TODO: Pass slice_per_pkt = {p.dsc_slice_per_pkt} */
	ctx->dsc.slice_height = {p.dsc_slice_height};
	ctx->dsc.slice_width = {p.dsc_slice_width};
	/*
	 * TODO: hdisplay should be read from the selected mode once
	 * it is passed back to drm_panel (in prepare?)
	 */
	WARN_ON({p.h.px} % ctx->dsc.slice_width);
	ctx->dsc.slice_count = {p.h.px} / ctx->dsc.slice_width;
	ctx->dsc.bits_per_component = {p.dsc_bit_per_component};
	ctx->dsc.bits_per_pixel = {p.dsc_bit_per_pixel} << 4; /* 4 fractional bits */
	ctx->dsc.block_pred_enable = {"true" if p.dsc_block_prediction else "false"};
'''

	s += '''
	ret = mipi_dsi_attach(dsi);
	if (ret < 0) {
		drm_panel_remove(&ctx->panel);
		return dev_err_probe(dev, ret, "Failed to attach to DSI host\\n");
	}
'''

	s += '''
	return 0;
}
'''
	return s


def generate_driver(p: Panel, options: Options) -> None:
	# Generate command sequences early
	for cmd in p.cmds.values():
		for c in cmd.seq:
			c.generated = c.type.generate(c.payload, options)
			cmd.generated += c.generated

	options.gpios = {}
	if p.reset_seq:
		# Many panels have active low reset GPIOs. This can be seen if we keep
		# reset high after turning the panel on. From a logical perspective this
		# does not make sense: We should assert reset to actually do the reset,
		# not to disable it.
		#
		# Therefore we try check the last element from the reset sequence here.
		# If it sets the GPIO to 1 (high), we assume that reset is active low.

		flag = GpioFlag.ACTIVE_HIGH
		last_val, _ = p.reset_seq[-1]
		if last_val == 1:
			flag = GpioFlag.ACTIVE_LOW

		options.gpios["reset"] = flag
	if options.backlight_gpio:
		options.gpios["backlight"] = GpioFlag.ACTIVE_HIGH

	dash_id = p.short_id.replace('_', '-')
	compatible = dash_id.split('-', 1)

	# Try to guess if short id starts with vendor name (e.g. booyi)
	if compatible[0].isalpha():
		compatible = ','.join(compatible)
	else:
		# Unknown vendor
		compatible = 'mdss,' + '-'.join(compatible)

	options.compatible = compatible

	module = f"panel-{dash_id}"
	with open(f'{p.id}/{module}.c', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) {datetime.date.today().year} FIXME
// Generated with linux-mdss-dsi-panel-driver-generator from vendor device tree:
//   Copyright (c) 2013, The Linux Foundation. All rights reserved. (FIXME)
{generate_includes(p, options)}

{generate_struct(p, options)}{generate_regulator_bulk(p, options)}

{wrap.simple([f'static inline', f'struct {p.short_id} *to_{p.short_id}(struct drm_panel *panel)'])}
{{
	return container_of(panel, struct {p.short_id}, panel);
}}
{generate_reset(p, options)}
{generate_commands(p, options, 'on')}
{generate_commands(p, options, 'off')}
{generate_prepare(p, options)}
{generate_unprepare(p, options)}
{simple.generate_mode(p)}
{wrap.join(f'static int {p.short_id}_get_modes(', ',', ')', ['struct drm_panel *panel', 'struct drm_connector *connector'])}
{{
	return drm_connector_helper_get_modes_fixed(connector, &{p.short_id}_mode);
}}

static const struct drm_panel_funcs {p.short_id}_panel_funcs = {{
	.prepare = {p.short_id}_prepare,
	.unprepare = {p.short_id}_unprepare,
	.get_modes = {p.short_id}_get_modes,
}};

{generate_backlight(p, options)}{generate_probe(p, options)}
static void {p.short_id}_remove(struct mipi_dsi_device *dsi)
{{
	struct {p.short_id} *ctx = mipi_dsi_get_drvdata(dsi);
	int ret;

	ret = mipi_dsi_detach(dsi);
	if (ret < 0)
		dev_err(&dsi->dev, "Failed to detach from DSI host: %d\\n", ret);

	drm_panel_remove(&ctx->panel);
}}

static const struct of_device_id {p.short_id}_of_match[] = {{
	{{ .compatible = "{compatible}" }}, // FIXME
	{{ /* sentinel */ }}
}};
MODULE_DEVICE_TABLE(of, {p.short_id}_of_match);

static struct mipi_dsi_driver {p.short_id}_driver = {{
	.probe = {p.short_id}_probe,
	.remove = {p.short_id}_remove,
	.driver = {{
		.name = "{module}",
		.of_match_table = {p.short_id}_of_match,
	}},
}};
module_mipi_dsi_driver({p.short_id}_driver);

MODULE_AUTHOR("linux-mdss-dsi-panel-driver-generator <fix@me>"); // FIXME
MODULE_DESCRIPTION("DRM driver for {p.name}");
MODULE_LICENSE("GPL");
''')
