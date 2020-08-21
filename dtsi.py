from generator import Options
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
	for r in options.gpios:
		s += f"\t\t{r}-gpios = <&msmgpio XY GPIO_ACTIVE_HIGH>;\n"
	return s


def generate_panel_dtsi(p: Panel, options: Options) -> None:
	name = p.short_id.replace('_', '-')
	with open(f'{p.id}/panel-{name}.dtsi', 'w') as f:
		f.write(f'''\
&dsi0 {{
	panel@0 {{
		compatible = "{options.compatible}";
		reg = <0>;

{generate_backlight(p)}\
{generate_supplies(options)}\
{generate_gpios(options)}\

		port {{
			panel_in: endpoint {{
				remote-endpoint = <&dsi0_out>;
			}};
		}};
	}};
}};

&dsi0_out {{
	data-lanes = <{' '.join(map(str, p.lane_map.phys2log[:p.lanes]))}>;
	remote-endpoint = <&panel_in>;
}};
''')
