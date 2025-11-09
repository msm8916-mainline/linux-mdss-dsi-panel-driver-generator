#!/usr/bin/env python3
import struct
import sys
from dataclasses import dataclass
from typing import Tuple

QCDT_MAGIC = 'QCDT'.encode()

HEADER_FORMAT = '<4sII'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

PAGE_SIZE = 2048
ENTRY_FORMATS = (
	'<IIIII',
	'<IIIIII',
	'<IIIIIIIIII',
)


@dataclass
class DTRecord:
	plat_id: int
	variant_id: int
	subtype_id: int
	offset: int
	size: int
	soc_rev: int = 0
	pmic: Tuple[int, int, int, int] = (0, 0, 0, 0)


with open(sys.argv[1], 'rb') as f:
	b = f.read()

magic, version, n = struct.unpack(HEADER_FORMAT, b[:HEADER_SIZE])
if magic != QCDT_MAGIC:
	print("Image does not appear to be an QCDT image")
	exit(1)

print(f'Version: {version}, Count: {n}')

records = []

offset = HEADER_SIZE
for i in range(0, n):
	entry_format = ENTRY_FORMATS[version - 1]
	size = struct.calcsize(entry_format)
	entry = struct.unpack(entry_format, b[offset:offset + size])
	offset += size

	r = DTRecord(entry[0], entry[1], entry[2], entry[-2], entry[-1])

	if version >= 2:
		r.soc_rev = entry[3]
	if version >= 3:
		r.pmic = (entry[4], entry[5], entry[6], entry[7])

	print(r)
	records.append(r)

for r in records:
	with open(f'plat_{r.plat_id:x}-var_{r.variant_id:x}-sub_{r.subtype_id:x}.dtb', 'wb') as f:
		f.write(b[r.offset:r.offset + r.size])
