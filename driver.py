# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import mipi
import simple
import wrap
from generator import Options
from panel import Panel, BacklightControl, CommandSequence


def generate_includes(p: Panel, options: Options) -> str:
	includes = {
		'linux': {
			'module.h',
			'delay.h',
			'of.h',
		},
		'video': set(),
		'drm': {
			'drm_mipi_dsi.h',
			'drm_modes.h',
			'drm_panel.h',
		},
	}

	if p.reset_seq:
		includes['linux'].add('gpio/consumer.h')
	if options.regulator:
		includes['linux'].add('regulator/consumer.h')
	if p.backlight == BacklightControl.DCS:
		includes['linux'].add('backlight.h')

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

	if options.regulator:
		if len(options.regulator) > 1:
			variables.append(f'struct regulator_bulk_data supplies[{len(options.regulator)}]')
		else:
			variables.append('struct regulator *supply')
	variables += [f'struct gpio_desc *{name}_gpio' for name in options.gpios]
	variables.append('bool prepared')

	s = f'struct {p.short_id} {{'
	for v in variables:
		s += '\n'
		if v:
			s += '\t' + v + ';'
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


def generate_reset(p: Panel) -> str:
	if not p.reset_seq:
		return ''

	s = f'\nstatic void {p.short_id}_reset(struct {p.short_id} *ctx)\n{{\n'
	for state, sleep in p.reset_seq:
		s += f'\tgpiod_set_value_cansleep(ctx->reset_gpio, {state});\n'
		if sleep:
			s += f'\t{msleep(sleep)};\n'
	s += '}\n'

	return s


def generate_commands(p: Panel, options: Options, cmd_name: str) -> str:
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
		if c.wait and c.wait > options.ignore_wait:
			s += f'\t{msleep(c.wait)};\n'

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


def generate_backlight(p: Panel, options: Options) -> str:
	if p.backlight != BacklightControl.DCS:
		return ''

	brightness_mask = ' & 0xff'
	if p.max_brightness > 255:
		brightness_mask = ''

	s = f'''\
static int {p.short_id}_bl_update_status(struct backlight_device *bl)
{{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
'''
	if options.backlight_gpio:
		s += f'\tstruct {p.short_id} *ctx = mipi_dsi_get_drvdata(dsi);\n'

	s += '''\
	u16 brightness = bl->props.brightness;
	int ret;

	if (bl->props.power != FB_BLANK_UNBLANK ||
	    bl->props.fb_blank != FB_BLANK_UNBLANK ||
	    bl->props.state & (BL_CORE_SUSPENDED | BL_CORE_FBBLANK))
		brightness = 0;
'''

	if options.backlight_gpio:
		s += '''
	gpiod_set_value_cansleep(ctx->backlight_gpio, !!brightness);
'''

	s += f'''
	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_set_display_brightness(dsi, brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return 0;
}}

static int {p.short_id}_bl_get_brightness(struct backlight_device *bl)
{{
	struct mipi_dsi_device *dsi = bl_get_data(bl);
	u16 brightness = bl->props.brightness;
	int ret;

	dsi->mode_flags &= ~MIPI_DSI_MODE_LPM;

	ret = mipi_dsi_dcs_get_display_brightness(dsi, &brightness);
	if (ret < 0)
		return ret;

	dsi->mode_flags |= MIPI_DSI_MODE_LPM;

	return brightness{brightness_mask};
}}

static const struct backlight_ops {p.short_id}_bl_ops = {{
	.update_status = {p.short_id}_bl_update_status,
	.get_brightness = {p.short_id}_bl_get_brightness,
}};
'''
	s += f'''
static struct backlight_device *
{p.short_id}_create_backlight(struct mipi_dsi_device *dsi)
{{
	struct device *dev = &dsi->dev;
	struct backlight_properties props = {{
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

	for name in options.gpios:
		s += f'''
	ctx->{name}_gpio = devm_gpiod_get(dev, "{name}", GPIOD_OUT_LOW);
	if (IS_ERR(ctx->{name}_gpio)) {{
		ret = PTR_ERR(ctx->{name}_gpio);
		dev_err(dev, "Failed to get {name}-gpios: %d\\n", ret);
		return ret;
	}}
'''

	s += f'''
	ctx->dsi = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);

	dsi->lanes = {p.lanes};
	dsi->format = {p.format};
{wrap.join('	dsi->mode_flags = ', ' |', ';', p.flags)}

	drm_panel_init(&ctx->panel, dev, &{p.short_id}_panel_funcs,
		       DRM_MODE_CONNECTOR_DSI);
'''

	if p.backlight == BacklightControl.DCS:
		s += f'''
	ctx->panel.backlight = {p.short_id}_create_backlight(dsi);
	if (IS_ERR(ctx->panel.backlight)) {{
		ret = PTR_ERR(ctx->panel.backlight);
		dev_err(dev, "Failed to create backlight: %d\\n", ret);
		return ret;
	}}
'''
	elif p.backlight:
		s += '''
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret) {
		dev_err(dev, "Failed to get backlight: %d\\n", ret);
		return ret;
	}
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

	options.gpios = []
	if p.reset_seq:
		options.gpios.append('reset')
	if options.backlight_gpio:
		options.gpios.append('backlight')

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
{generate_commands(p, options, 'on')}
{generate_commands(p, options, 'off')}
{generate_prepare(p, options)}
{generate_unprepare(p, options)}
{simple.generate_mode(p)}
{wrap.join(f'static int {p.short_id}_get_modes(', ',', ')', ['struct drm_panel *panel', 'struct drm_connector *connector'])}
{{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &{p.short_id}_mode);
	if (!mode)
		return -ENOMEM;

	drm_mode_set_name(mode);

	mode->type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
	connector->display_info.width_mm = mode->width_mm;
	connector->display_info.height_mm = mode->height_mm;
	drm_mode_probed_add(connector, mode);

	return 1;
}}

static const struct drm_panel_funcs {p.short_id}_panel_funcs = {{
	.prepare = {p.short_id}_prepare,
	.unprepare = {p.short_id}_unprepare,
	.get_modes = {p.short_id}_get_modes,
}};

{generate_backlight(p, options)}{generate_probe(p, options)}
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

MODULE_AUTHOR("linux-mdss-dsi-panel-driver-generator <fix@me>");
MODULE_DESCRIPTION("DRM driver for {p.name}");
MODULE_LICENSE("GPL v2");
''')
