#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import struct
import sys

BOOT_MAGIC = 'ANDROID!'.encode()

HEADER_FORMAT = '<8s10I16s512s32s1024s'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def extract_file(f, name, pos, size):
	f.seek(pos)
	with open(name, 'wb') as o:
		o.write(f.read(size))


def unpack_image(f):
	header = struct.unpack(HEADER_FORMAT, f.read(HEADER_SIZE)[:HEADER_SIZE])

	# Ensure this is an Android boot image
	if header[0] != BOOT_MAGIC:
		print("Image does not appear to be an Android boot image")
		exit(1)

	page_size = header[8]
	page_mask = page_size - 1

	offset = page_size

	kernel_size = header[1]
	if kernel_size:
		extract_file(f, 'kernel.img', offset, kernel_size)
		offset += (kernel_size + page_mask) & ~page_mask

	ramdisk_size = header[3]
	if ramdisk_size:
		extract_file(f, 'ramdisk.img', offset, ramdisk_size)
		offset += (ramdisk_size + page_mask) & ~page_mask

	second_size = header[5]
	if second_size:
		extract_file(f, 'second.img', offset, second_size)
		offset += (second_size + page_mask) & ~page_mask

	dtb_size = header[9]
	if dtb_size > 1:
		extract_file(f, 'dtb.img', offset, dtb_size)
		offset += (dtb_size + page_mask) & ~page_mask

	# Extract command line
	cmdline = header[12].decode().rstrip('\0') + header[14].decode().rstrip('\0')

	with open('cmdline.txt', 'w') as o:
		o.write(cmdline)


with open(sys.argv[1], 'rb') as f:
	unpack_image(f)
