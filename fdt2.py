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

	def subnode_or_none(self, parentoffset, name):
		offset = self.subnode_offset(parentoffset, name, [FDT_ERR_NOTFOUND])
		if offset == -FDT_ERR_NOTFOUND:
			return None
		return offset

	def getprop(self, nodeoffset, prop_name, quiet=()):
		try:
			return super().getprop(nodeoffset, prop_name, quiet)
		except:
			print(f"ERROR: Failed to get property: {prop_name}")
			raise

	def getprop_or_none(self, nodeoffset, prop_name):
		prop = self.getprop(nodeoffset, prop_name, [FDT_ERR_NOTFOUND])
		if prop == -FDT_ERR_NOTFOUND:
			return None
		return prop

	def getprop_uint32(self, nodeoffset, prop_name, default=0, ignore_empty=False):
		prop = self.getprop(nodeoffset, prop_name, [FDT_ERR_NOTFOUND])
		if prop == -FDT_ERR_NOTFOUND:
			return default
		if ignore_empty and len(prop) == 0:
			return default
		return prop.as_uint32()


def property_is_str(self):
	return self[-1] == 0 and 0 not in self[:-1]


def property_as_uint32_array(self):
	num = int(len(self) / 4)
	return list(struct.unpack('>' + ('L' * num), self))


Property.is_str = property_is_str
Property.as_uint32_array = property_as_uint32_array
