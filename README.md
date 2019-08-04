# linux-mdss-dsi-panel-driver-generator (lmdpdg)
The downstream kernel for Qualcomm-based Android devices describes panel
properties and initialization sequences in the device tree.  
(See [DSI Panel Driver Porting] for details)

This tool uses the information provided in the device tree to automatically
generate a simple DRM panel driver, for use in mainline together with Freedreno.
As far as possible, it attempts to generate _clean_ C code, so that only minimal
changes are necessary for upstreaming the generated panel driver.

**Example:**
  - Input device tree:
  [`dsi_panel_S6E88A0_AMS452EF01_qhd_octa_video.dtsi`](https://gist.github.com/Minecrell/56c2b20118ba00a9723f0785301bc5ec#file-dsi_panel_s6e88a0_ams452ef01_qhd_octa_video-dtsi) 
  - Generated panel driver:
  [`panel-s6e88a0-ams452ef01.c`](https://gist.github.com/Minecrell/bc5fbfc3ba98873d32c07793d6997172#file-panel-s6e88a0-ams452ef01-c),
  [`panel-simple-s6e88a0-ams452ef01.c`](https://gist.github.com/Minecrell/bc5fbfc3ba98873d32c07793d6997172#file-panel-simple-s6e88a0-ams452ef01-c)

## Preparation
### Requirements
- Python 3.7+
- [pylibfdt] compiled for Python 3

### Extracting device tree blob (DTB)
lmdpdg operates on the compiled device tree blob (dtb), not the original source
file from the kernel source. This means that it can be easily used even when the
kernel source is not available.

The device tree blob can be easily extracted from a stock boot image (`boot.img`):

```shell
$ tools/unpackbootimg.py boot.img
$ tools/unpackqcdt.py dt.img
```

This will produce multiple `*.dtb` files in the correct directory.
You will need to try multiple (or all) of them to find the correct one.

### Compiling from source `.dtsi`
If you have only the source `.dtsi` for the panel, or would like to make changes
in it, you can still use it as input for this tool. You just need to pretend
to have a full device tree blob by setting up the needed device nodes:

```dts
/dts-v1/;

/ {
	mdp {
		compatible = "qcom,mdss_mdp";

		/* Add your panels here */
		dsi_sim_vid: qcom,mdss_dsi_sim_video {
			qcom,mdss-dsi-panel-name = "Simulator video mode dsi panel";
			//qcom,mdss-dsi-panel-controller = <&mdss_dsi0>;
			qcom,mdss-dsi-panel-type = "dsi_video_mode";
			/* ... */
		};
	};
};
```

Comment out entries that refer to other devices (see above).

Compile it using [dtc]: `dtc -O your.dtb your.dts`. That's it! Yay!

## Usage
Got the device tree blob? Then you are ready to go:

```shell
$ python lmdpdg.py <dtbs...>
```

The generator has a couple of command line options that can be used to generate
additional code (e.g. to enable a regulator to power on the panel).
The script will gladly inform you about available options if you pass `--help`.

### Making final edits
In most cases, the driver should work as-is, no changes required.
If you would like to use it permanently, or even upstream it, here are a few
things that you may want to update:

  - The `compatible` string in the device tree match table
  - `MODULE_AUTHOR`
  - `MODULE_DESCRIPTION` (eventually)
  - License header
  - If you have comments in your device tree source file
	(e.g. for the on/off command sequence), you may want to apply them to the
	driver to make the code a bit less magic.

Adding it to `drivers/gpu/drm/panel`, together with adding needed `Kconfig`
and `Makefile` entries should be straightforward.

## Warning
This tool is like a human: it can make mistakes. Nobody knows what will happen
to your panel if you send it bad commands or turn it on incorrectly. In most
cases it will just refuse to work.

However, this tool is mainly intended as a helping hand when porting new panels.
You should verify that its output makes sense before using the generated driver.

## Questions?
Feel free to open an issue! :)

[dtc]: https://git.kernel.org/pub/scm/utils/dtc/dtc.git
[pylibfdt]: https://git.kernel.org/pub/scm/utils/dtc/dtc.git
[DSI Panel Driver Porting]: https://github.com/freedreno/freedreno/wiki/DSI-Panel-Driver-Porting
