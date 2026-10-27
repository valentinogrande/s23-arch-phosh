import sys

path = sys.argv[1]
src = open(path).read()

old = """			if (!has_drm_props) {
				wlr_log(WLR_DEBUG, "  Ignoring physical device \\"%s\\": "
"""
new = """			if (!has_drm_props && getenv("WLR_VK_KGSL") &&
					phdev_props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU) {
				// Android/KGSL: la GPU no tiene nodo DRM, la pantalla es otro dispositivo.
				wlr_log(WLR_INFO, "Using KGSL Vulkan physical device: %s",
					phdev_props.deviceName);
				return phdev;
			}
			if (!has_drm_props) {
				wlr_log(WLR_DEBUG, "  Ignoring physical device \\"%s\\": "
"""
if "WLR_VK_KGSL" in src:
    print("already patched")
    sys.exit(0)
assert src.count(old) == 1, "pattern not found"
src = src.replace(old, new)
if "#include <stdlib.h>" not in src:
    src = "#include <stdlib.h>\n" + src
open(path, "w").write(src)
print("patched")
