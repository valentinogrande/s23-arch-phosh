import sys

path = sys.argv[1]
src = open(path).read()

old = "\tdev->drm_fd = vulkan_open_phdev_drm_fd(phdev);\n"
new = """\tdev->drm_fd = vulkan_open_phdev_drm_fd(phdev);
\tif (dev->drm_fd < 0 && drm_fd >= 0) {
\t\t// KGSL: la GPU no tiene nodo DRM, usamos el de la pantalla para asignar buffers.
\t\tdev->drm_fd = fcntl(drm_fd, F_DUPFD_CLOEXEC, 0);
\t}
"""
if "KGSL: la GPU no tiene nodo DRM, usamos" in src:
    print("already patched")
    sys.exit(0)
assert src.count(old) == 1, "pattern not found"
src = src.replace(old, new)
if "#include <fcntl.h>" not in src:
    src = "#include <fcntl.h>\n" + src
open(path, "w").write(src)
print("patched")
