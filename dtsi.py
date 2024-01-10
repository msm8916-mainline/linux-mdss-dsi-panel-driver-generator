# SPDX-License-Identifier: GPL-2.0-only
from generator import Options, GpioFlag
from panel import Panel, BacklightControl


def generate_backlight(p: Panel):
	if p.backlight == BacklightControl.DCS:
		return ""
	return "\t\tbacklight = <&backlight>;\n"


def generate_supplies(options: Options):
	s = ""
	if options.regulator:
		for r in options.regulator:
			s += f"\t\t{r}-supply = <&...>;\n"
	return s


def generate_gpios(options: Options):
	s = ""
	for name, flags in options.gpios.items():
		flags = "GPIO_ACTIVE_LOW" if flags & GpioFlag.ACTIVE_LOW else "GPIO_ACTIVE_HIGH"
		s += f"\t\t{name}-gpios = <&tlmm XY {flags}>;\n"

	if 'backlight' in options.gpios:
		s += '''
		pinctrl-0 = <&lcd_bl_en_default>;
		pinctrl-names = "default";
'''
	return s


def generate_tlmm(options: Options):
	s = "&tlmm {"
	if 'backlight' in options.gpios:
		s += '''
	lcd_bl_en_default: lcd-bl-en-default-state {
		pins = "gpioXY";
		function = "gpio";
		drive-strength = <2>;
		bias-disable;
	};
'''

	s += '''
	mdss_default: mdss-default-state {
		pins = "gpioXY";
		function = "gpio";
		drive-strength = <8>;
		bias-disable;
	};

	mdss_sleep: mdss-sleep-state {
		pins = "gpioXY";
		function = "gpio";
		drive-strength = <2>;
		bias-pull-down;
	};
};
'''
	return s


def generate_panel_dtsi(p: Panel, options: Options) -> None:
	name = p.short_id.replace('_', '-')
	with open(f'{p.id}/panel-{name}.dtsi', 'w') as f:
		if p.cphy_mode:
			f.write('''\
#include <dt-bindings/phy/phy.h>

''')
		f.write(f'''\
&mdss_dsi0 {{
	pinctrl-0 = <&mdss_default>;
	pinctrl-1 = <&mdss_sleep>;
	pinctrl-names = "default", "sleep";

	panel@0 {{
		compatible = "{options.compatible}";
		reg = <0>;

{generate_backlight(p)}\
{generate_supplies(options)}\
{generate_gpios(options)}\

		port {{
			panel_in: endpoint {{
				remote-endpoint = <&mdss_dsi0_out>;
			}};
		}};
	}};
}};

&mdss_dsi0_out {{
	data-lanes = <{' '.join(map(str, p.lane_map.phys2log[:p.lanes]))}>;
	remote-endpoint = <&panel_in>;
}};
''')

		if p.ldo_mode:
			f.write('''
&mdss_dsi0_phy {
	qcom,dsi-phy-regulator-ldo-mode;
};
''')
		if p.cphy_mode:
			f.write('''
&mdss_dsi0_phy {
    phy-type = <PHY_TYPE_CPHY>;
};
''')

		f.write(generate_tlmm(options))
