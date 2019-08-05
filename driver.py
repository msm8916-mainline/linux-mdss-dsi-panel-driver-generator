# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import mipi
import simple
import wrap
from generator import Options
from panel import Panel, BacklightControl, CommandSequence


def generate_includes(p: Panel, options: Options) -> str:
	includes = {
		'drm/drm_mipi_dsi.h',
		'drm/drm_modes.h',
		'drm/drm_panel.h',
		'linux/module.h',
		'linux/delay.h'
	}

	if p.reset_seq:
		includes.add('linux/gpio/consumer.h')
	if options.regulator:
		includes.add('linux/regulator/consumer.h')
	if p.backlight:
		includes.add('linux/backlight.h')

	for cmd in p.cmds.values():
		if 'MIPI_DCS_' in cmd.generated:
			includes.add('video/mipi_display.h')
			break

	return '\n'.join(f'#include <{i}>' for i in sorted(includes))


def generate_struct(p: Panel, options: Options) -> str:
	variables = [
		'struct drm_panel panel;',
		'struct mipi_dsi_device *dsi;',
	]

	if p.backlight:
		variables.append('struct backlight_device *backlight;')
	if options.regulator:
		if len(options.regulator) > 1:
			variables.append(f'struct regulator_bulk_data supplies[{len(options.regulator)}];')
		else:
			variables.append('struct regulator *supply;')
	if p.reset_seq:
		variables.append('struct gpio_desc *reset_gpio;')

	variables += [
		'',
		'bool prepared;',
		'bool enabled;'
	]

	s = f'struct {p.short_id} {{'
	for v in variables:
		s += '\n'
		if v:
			s += '\t' + v
	s += '\n};'
	return s


def generate_macros(p: Panel) -> str:
	macros = set()
	for cmd in p.cmds.values():
		# Check which macros are necessary
		for macro in mipi.MACROS.keys():
			if macro in cmd.generated:
				macros.add(macro)

	s = ''
	for macro, expr in mipi.MACROS.items():
		if not macro in macros:
			continue
		s += f'''

#define {macro}(dsi, seq...) do {{				\\
		static const u8 d[] = {{ seq }};				\\
		int ret;						\\
		ret = {expr}(dsi, d, ARRAY_SIZE(d));	\\
		if (ret < 0)						\\
			return ret;					\\
	}} while (0)\
'''
	return s


def generate_reset(p: Panel) -> str:
	if not p.reset_seq:
		return ''

	s = f'\nstatic void {p.short_id}_reset(struct {p.short_id} *ctx)\n{{\n'
	for state, sleep in p.reset_seq:
		s += f'\tgpiod_set_value_cansleep(ctx->reset_gpio, {state});\n'
		if sleep:
			s += f'\tmsleep({sleep});\n'
	s += '}\n'

	return s


def generate_commands(p: Panel, cmd_name: str) -> str:
	s = f'''\
static int {p.short_id}_{cmd_name}(struct {p.short_id} *ctx)
{{
	struct mipi_dsi_device *dsi = ctx->dsi;
	struct device *dev = &dsi->dev;
	int ret;
'''
	cmd = p.cmds[cmd_name]

	if p.cmds['on'].state != p.cmds['off'].state:
		if cmd.state == CommandSequence.State.LP_MODE:
			s += '\n\tdsi->mode_flags |= MIPI_DSI_MODE_LPM;\n'
		elif cmd.state == CommandSequence.State.HS_MODE:
			s += '\n\tdsi->mode_flags &= ~MIPI_DSI_MODE_LPM;\n'

	block = True
	for c in cmd.seq:
		if block or '{' in c.generated:
			s += '\n'
		block = '{' in c.generated

		s += c.generated + '\n'
		if c.wait:
			s += f'\tmsleep({c.wait});\n'

	s += '''
	return 0;
}
'''
	return s


def generate_cleanup(p: Panel, options: Options, indent: int = 1) -> str:
	cleanup = []
	if p.reset_seq:
		cleanup.append('gpiod_set_value_cansleep(ctx->reset_gpio, 0);')
	if options.regulator:
		if len(options.regulator) > 1:
			cleanup.append('regulator_bulk_disable(ARRAY_SIZE(ctx->supplies), ctx->supplies);')
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
	int ret;

	if (ctx->prepared)
		return 0;
'''

	if options.regulator:
		if len(options.regulator) > 1:
			s += '''
	ret = regulator_bulk_enable(ARRAY_SIZE(ctx->supplies), ctx->supplies);
	if (ret < 0) {
		dev_err(dev, "Failed to enable regulators: %d\\n", ret);
		return ret;
	}
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

	ctx->prepared = true;
	return 0;
}}
'''
	return s


def generate_unprepare(p: Panel, options: Options) -> str:
	return f'''\
static int {p.short_id}_unprepare(struct drm_panel *panel)
{{
	struct {p.short_id} *ctx = to_{p.short_id}(panel);
	struct device *dev = &ctx->dsi->dev;
	int ret;

	if (!ctx->prepared)
		return 0;

	ret = {p.short_id}_off(ctx);
	if (ret < 0)
		dev_err(dev, "Failed to un-initialize panel: %d\\n", ret);
{generate_cleanup(p, options)}

	ctx->prepared = false;
	return 0;
}}
'''


def generate_backlight(p: Panel) -> str:
	if p.backlight != BacklightControl.DCS:
		return ''

	if p.max_brightness > 255:
		raise ValueError(f"Max brightness {p.max_brightness} > 255 is not supported yet")

	s = '''\
static int dsi_dcs_bl_get_brightness(struct backlight_device *bl)
{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
	int ret;
	u16 brightness = bl->props.brightness;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_get_display_brightness(dsi, &brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return brightness & 0xff;
}

static int dsi_dcs_bl_update_status(struct backlight_device *bl)
{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
	int ret;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_set_display_brightness(dsi, bl->props.brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return 0;
}

static const struct backlight_ops dsi_bl_ops = {
	.update_status = dsi_dcs_bl_update_status,
	.get_brightness = dsi_dcs_bl_get_brightness,
};
'''
	s += f'''
static struct backlight_device *
{p.short_id}_create_backlight(struct mipi_dsi_device *dsi)
{{
	struct device *dev = &dsi->dev;
	struct backlight_properties props;

	memset(&props, 0, sizeof(props));
	props.type = BACKLIGHT_RAW;
	props.brightness = {p.max_brightness or 255};
	props.max_brightness = {p.max_brightness or 255};

	return devm_backlight_device_register(dev, dev_name(dev), dev, dsi,
					      &dsi_bl_ops, &props);
}}

'''
	return s


def generate_probe(p: Panel, options: Options) -> str:
	s = f'''\
static int {p.short_id}_probe(struct mipi_dsi_device *dsi)
{{
	struct device *dev = &dsi->dev;
	struct {p.short_id} *ctx;
	int ret;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;
'''

	if options.regulator:
		if len(options.regulator) > 1:
			i = 0
			for i, r in enumerate(options.regulator):
				s += f'\n\tctx->supplies[{i}].supply = "{r}";'
			s += f'''
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(ctx->supplies),
				      ctx->supplies);
	if (ret < 0) {{
		dev_err(dev, "Failed to get regulators: %d\\n", ret);
		return ret;
	}}
'''
		else:
			s += f'''
	ctx->supply = devm_regulator_get(dev, "{options.regulator[0]}");
	if (IS_ERR(ctx->supply)) {{
		ret = PTR_ERR(ctx->supply);
		dev_err(dev, "Failed to get {options.regulator[0]} regulator: %d\\n", ret);
		return ret;
	}}
'''

	if p.reset_seq:
		s += '''
	ctx->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->reset_gpio)) {
		ret = PTR_ERR(ctx->reset_gpio);
		dev_err(dev, "Failed to get reset-gpios: %d\\n", ret);
		return ret;
	}
'''

	if p.backlight == BacklightControl.DCS:
		s += f'''
	ctx->backlight = {p.short_id}_create_backlight(dsi);
	if (IS_ERR(ctx->backlight)) {{
		ret = PTR_ERR(ctx->backlight);
		dev_err(dev, "Failed to create backlight: %d\\n", ret);
		return ret;
	}}
'''
	else:
		s += '''
	ctx->backlight = devm_of_find_backlight(dev);
	if (IS_ERR(ctx->backlight)) {
		ret = PTR_ERR(ctx->backlight);
		dev_err(dev, "Failed to get backlight: %d\\n", ret);
		return ret;
	}
'''

	s += f'''
	ctx->dsi = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);

	dsi->lanes = {p.lanes};
	dsi->format = {p.format};
{wrap.join('	dsi->mode_flags = ', ' |', ';', p.flags)}

	drm_panel_init(&ctx->panel);
	ctx->panel.dev = dev;
	ctx->panel.funcs = &{p.short_id}_panel_funcs;
'''

	s += '''
	ret = drm_panel_add(&ctx->panel);
	if (ret < 0) {
		dev_err(dev, "Failed to add panel: %d\\n", ret);
		return ret;
	}

	ret = mipi_dsi_attach(dsi);
	if (ret < 0) {
		dev_err(dev, "Failed to attach to DSI host: %d\\n", ret);
		return ret;
	}

	return 0;
}
'''
	return s


def generate_driver(p: Panel, options: Options) -> None:
	# Generate command sequences early
	for cmd in p.cmds.values():
		for c in cmd.seq:
			c.generated = c.type.generate(c.payload)
			cmd.generated += c.generated

	module = f"panel-{p.short_id.replace('_', '-')}"
	with open(f'{p.id}/{module}.c', 'w') as f:
		f.write(f'''\
// SPDX-License-Identifier: GPL-2.0-only
// Copyright (c) 2013, The Linux Foundation. All rights reserved.

{generate_includes(p, options)}

{generate_struct(p, options)}

static inline struct {p.short_id} *to_{p.short_id}(struct drm_panel *panel)
{{
	return container_of(panel, struct {p.short_id}, panel);
}}{generate_macros(p)}
{generate_reset(p)}
{generate_commands(p, 'on')}
{generate_commands(p, 'off')}
{generate_prepare(p, options)}
{generate_unprepare(p, options)}
static int {p.short_id}_enable(struct drm_panel *panel)
{{
	struct {p.short_id} *ctx = to_{p.short_id}(panel);
	int ret;

	if (ctx->enabled)
		return 0;

	ret = backlight_enable(ctx->backlight);
	if (ret < 0) {{
		dev_err(&ctx->dsi->dev, "Failed to enable backlight: %d\\n", ret);
		return ret;
	}}

	ctx->enabled = true;
	return 0;
}}

static int {p.short_id}_disable(struct drm_panel *panel)
{{
	struct {p.short_id} *ctx = to_{p.short_id}(panel);
	int ret;

	if (!ctx->enabled)
		return 0;

	ret = backlight_disable(ctx->backlight);
	if (ret < 0) {{
		dev_err(&ctx->dsi->dev, "Failed to disable backlight: %d\\n", ret);
		return ret;
	}}

	ctx->enabled = false;
	return 0;
}}

{simple.generate_mode(p)}
static int {p.short_id}_get_modes(struct drm_panel *panel)
{{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(panel->drm, &{p.short_id}_mode);
	if (!mode)
		return -ENOMEM;

	drm_mode_set_name(mode);

	mode->type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
	panel->connector->display_info.width_mm = mode->width_mm;
	panel->connector->display_info.height_mm = mode->height_mm;
	drm_mode_probed_add(panel->connector, mode);

	return 1;
}}

static const struct drm_panel_funcs {p.short_id}_panel_funcs = {{
	.disable = {p.short_id}_disable,
	.unprepare = {p.short_id}_unprepare,
	.prepare = {p.short_id}_prepare,
	.enable = {p.short_id}_enable,
	.get_modes = {p.short_id}_get_modes,
}};

{generate_backlight(p)}{generate_probe(p, options)}
static int {p.short_id}_remove(struct mipi_dsi_device *dsi)
{{
	struct {p.short_id} *ctx = mipi_dsi_get_drvdata(dsi);
	int ret;

	ret = mipi_dsi_detach(dsi);
	if (ret < 0)
		dev_err(&dsi->dev, "Failed to detach from DSI host: %d\\n", ret);

	drm_panel_remove(&ctx->panel);

	return 0;
}}

static const struct of_device_id {p.short_id}_of_match[] = {{
	{{ .compatible = "mdss,{p.short_id}" }}, // FIXME
	{{ }}
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

MODULE_AUTHOR("linux-mdss-dsi-panel-driver-generator <fix@me>");
MODULE_DESCRIPTION("DRM driver for {p.name}");
MODULE_LICENSE("GPL v2");
''')
