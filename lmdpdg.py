# SPDX-License-Identifier: GPL-2.0-only
import argparse
import os
import shutil

import generator
from driver import generate_driver
from fdt2 import Fdt2
from panel import Panel
from simple import generate_panel_simple


def generate(p: Panel, options: generator.Options) -> None:
	print(f"Generating: {p.id} ({p.name})")

	if os.path.exists(p.id):
		shutil.rmtree(p.id)
	os.mkdir(p.id)

	if not args.backlight:
		p.backlight = None

	generate_panel_simple(p)
	generate_driver(p, options)


parser = argparse.ArgumentParser(
	description="Generate Linux DRM panel driver based on (downstream) MDSS DSI device tree")
parser.add_argument('dtb', nargs='+', type=argparse.FileType('rb'), help="Device tree blobs to parse")
parser.add_argument('-r', '--regulator', action='append', nargs='?', const='power', help="""
	Enable one or multiple regulators with the specified name in the generated panel driver.
	Some panels require additional power supplies to be enabled to work properly.
""")
parser.add_argument('--backlight-gpio', action='store_true', help="""
	Enable/disable backlight with an extra GPIO (works only for MIPI DCS backlight)
""")
parser.add_argument('--no-backlight', dest='backlight', action='store_false', default=True, help="""
	Do not generate any backlight/brightness related code.
""")
parser.add_argument('--ignore-wait', type=int, default=0, help="""
	Ignore wait in command sequences that is smaller that the specified value.
	Some device trees add a useless 1ms wait after each command, making the driver
	unnecessarily verbose.
""")
args = parser.parse_args(namespace=generator.Options())

for f in args.dtb:
	with f:
		print(f"Parsing: {f.name}")
		fdt = Fdt2(f.read())

		found = False
		for panel in Panel.find(fdt):
			found = True
			generate(panel, args)

		if not found:
			print(f"{f.name} does not contain any panel specifications")
