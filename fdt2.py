# SPDX-License-Identifier: GPL-2.0-only

# Extend libfdt with some utility methods
from libfdt import *


class Fdt2(FdtRo):
	def find_by_compatible(self, compatible):
		offset = -1
		while True:
			offset = check_err(
				fdt_node_offset_by_compatible(self._fdt, offset, compatible),
				[FDT_ERR_NOTFOUND])
			if offset == -FDT_ERR_NOTFOUND:
				break
			yield offset

	def subnodes(self, parent):
		offset = self.first_subnode(parent, [FDT_ERR_NOTFOUND])
		while offset != -FDT_ERR_NOTFOUND:
			yield offset
			offset = self.next_subnode(offset, [FDT_ERR_NOTFOUND])

	def getprop_or_none(self, nodeoffset, prop_name):
		prop = self.getprop(nodeoffset, prop_name, [FDT_ERR_NOTFOUND])
		if prop == -FDT_ERR_NOTFOUND:
			return None
		return prop

	def getprop_int32(self, nodeoffset, prop_name, default=0):
		prop = self.getprop(nodeoffset, prop_name, [FDT_ERR_NOTFOUND])
		if prop == -FDT_ERR_NOTFOUND:
			return default
		return prop.as_int32()
