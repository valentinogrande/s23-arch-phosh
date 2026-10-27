"""phoc: con PHOC_NO_DPMS ignorar los pedidos de apagar la salida (wlr-output-power).
En el S23 apagar el panel por msm_drm sin el HAL de Samsung cuelga el equipo."""
import sys

path = sys.argv[1]
src = open(path).read()
if "PHOC_NO_DPMS" in src:
    print("already patched")
    sys.exit(0)
old = """  self = event->output->data;
  g_debug ("Request to set output power mode of %p to %d", self->wlr_output->name, event->mode);
"""
new = """  self = event->output->data;
  g_debug ("Request to set output power mode of %p to %d", self->wlr_output->name, event->mode);
  if (g_getenv ("PHOC_NO_DPMS")) {
    g_debug ("PHOC_NO_DPMS set, ignoring power mode request");
    return;
  }
"""
assert src.count(old) == 1, "pattern not found"
open(path, "w").write(src.replace(old, new))
print("patched")
