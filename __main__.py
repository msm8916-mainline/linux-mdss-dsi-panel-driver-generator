# SPDX-License-Identifier: GPL-2.0-only
import argparse
import os
import shutil

from driver import generate_driver
from fdt2 import Fdt2
from panel import Panel
from simple import generate_panel_simple


def generate(p: Panel) -> None:
	print(f"Generating: {p.id} ({p.name})")

	if os.path.exists(p.id):
		shutil.rmtree(p.id)
	os.mkdir(p.id)

	generate_panel_simple(p)
	generate_driver(p)


parser = argparse.ArgumentParser(
	description="Generate Linux DRM panel driver based on (downstream) MDSS DSI device tree")
parser.add_argument('dtb', nargs='+', type=argparse.FileType('rb'), help="Device tree blobs to parse")
parser.add_argument('-r', '--regulator', nargs='?', const='power', help="Enable panel power supply through regulator")
args = parser.parse_args()

for f in args.dtb:
	with f:
		print(f"Parsing: {f.name}")
		fdt = Fdt2(f.read())

		found = False
		for panel in Panel.find(fdt):
			found = True
			panel.regulator = args.regulator
			generate(panel)

		if not found:
			print(f"{f.name} does not contain any panel specifications")
