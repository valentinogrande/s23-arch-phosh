# Arch Linux + Phosh nativo en Galaxy S23 (bootloader bloqueado)

> **EN:** Arch Linux ARM (chroot) running **Phosh directly on the display** of a Samsung
> Galaxy S23 (SM-S911B, Snapdragon 8 Gen 2) with a **locked bootloader** and only a
> temporary root (KernelSU). Android's display stack is stopped, Linux takes over the
> panel through DRM, while Android's `system_server` keeps running for Wi-Fi, audio and
> sensors. GPU-accelerated compositor (Turnip on KGSL), touch, audio, rotation,
> brightness, battery and power button all work. Notes below are in Spanish.

Tocás un ícono en Android y el teléfono pasa a ser un Linux de celular (Phosh) a pantalla
completa. Para volver, el teléfono se reinicia a Android.

**Todo vive en `/data`.** Nada de fastboot, nada de flashear, no se toca ninguna
partición (boot, system, vendor, vbmeta). El bootloader sigue bloqueado y Knox intacto.

## Qué funciona

| | |
|---|---|
| Pantalla | phoc (wlroots) directo sobre `/dev/dri/card0` (msm_drm, DSI-1 1080×2340) |
| GPU | El compositor renderiza con Vulkan: Turnip (Mesa) sobre **KGSL**, el driver de GPU de Android |
| Touch | `sec_touchscreen` vía libinput |
| Wi-Fi | La conexión de Android, compartida (mismo namespace de red) |
| Audio | PipeWire → FIFO → `AudioTrack` de Android |
| Rotación | Acelerómetro de Android → iio-sensor-proxy falso → Phosh |
| Brillo, batería | logind falso (`SetBrightness`) y upower |
| Botón de encendido | "Apaga" la pantalla (negro + touch off) y bloquea |
| Teclado | Stevia (sugerencias con hunspell, emojis, deslizar) |
| Apps | Firefox (con mobile-config-firefox), Consola, Archivos, etc. — renderizan por CPU |

No funciona: GPU para las apps (cuelga el equipo), llamadas/SMS/datos móviles, cámara,
cambiar de Wi-Fi desde Linux, volver a Android sin reiniciar.

## Cómo funciona

```
 Android (sigue vivo)                          Linux (chroot /data/local/arch)
 ───────────────────                           ───────────────────────────────
 system_server, netd, wpa_supplicant  ◄─red──  apps (misma red que Android)
 audioserver ◄── DroidBridge (app_process) ◄── PipeWire (pipe-sink FIFO)
 sensorservice ──► DroidBridge ──────────────► fake-logind (net.hadess.SensorProxy) ─► Phosh
 surfaceflinger      ✗ frenado                 phoc ── DRM/KMS card0 ── panel
 composer HAL        ✗ frenado                      └─ Vulkan Turnip ── /dev/kgsl-3d0
 apps (uid ≥ 10000)  ❄ congeladas (cgroup freezer)
```

1. `native start` frena **solo** `surfaceflinger` y el composer de Qualcomm
   (`setprop ctl.stop`), que liberan el DRM master. `zygote` y `system_server` siguen
   vivos, así que el Wi-Fi sigue conectado.
2. Arranca la sesión en la chroot: dbus, seatd (`SEATD_VTBOUND=0`), fake-logind, phoc y
   Phosh.
3. Congela todas las apps de Android (`/sys/fs/cgroup/apps/uid_*/cgroup.freeze`).
4. Para volver: reinicio normal (`/system/bin/reboot`, sin argumentos). Reiniciar Android
   "en caliente" deja el sistema a medias.

## Lo que aprendimos (las trampas)

Esto es lo valioso del repo. Cada punto costó uno o varios cuelgues.

- **Softdog de Samsung = kernel panic a los 100 s.** `system_server` alimenta un watchdog
  de software (`WatchdogSoftdog`); si se muere o su Watchdog se traba, el kernel entra en
  pánico (`Software Watchdog Timer expired 100s`). Se desactiva con
  `setprop persist.vendor.softdog off` (persiste en `/data`, aplica al reiniciar).
- **El watchdog de `system_server` también.** Con surfaceflinger frenado, cualquier
  llamada de `system_server` a SF se queda esperando para siempre y el watchdog lo mata
  a los ~60 s. La clave que funciona en Samsung es
  `settings put global system_server_watchdog_timeout_ms 86400000` (no `watchdog_timeout`).
  **No la dejes puesta al reiniciar con el softdog activo**: el Watchdog deja de
  alimentar al softdog y entra en un loop de pánicos a los 100 s de cada arranque.
- **`zygote` es `critical`:** 4 caídas en 4 minutos → init reinicia a bootloader
  (Download mode en Samsung). Por eso no se frena zygote.
- **Nunca apagar el panel (DPMS) por msm_drm:** cuelga el equipo (watchdog de hardware).
  phoc está parcheado (`PHOC_NO_DPMS`) para ignorarlo; "apagar pantalla" es brillo 0 +
  una capa negra (OLED) + touch off.
- **Ninguna app Linux puede usar la GPU.** El Mesa de Arch trae `kgsl_dri.so`
  (freedreno sobre KGSL): Firefox y GTK lo agarran solos y el teléfono se cuelga. Las
  apps corren con `LIBGL_ALWAYS_SOFTWARE=1`, `GSK_RENDERER=cairo` y sin Vulkan. zink
  sobre Turnip también cuelga. Solo phoc usa la GPU.
- **wlroots no acepta Turnip-KGSL** (no tiene `VK_EXT_physical_device_drm`). Parche en
  `patches/wlroots/` + phoc compilado con wlroots embebido. El phoc de Arch además
  rompe con Phosh (`phosh home`, protocol error 71).
- **`runuser` desde un `adb su` con la sesión corriendo cuelga el teléfono** (pasa por
  PAM). Para correr cosas como el usuario: `setpriv --reuid=… --init-groups`.
- **No tocar `wlan0`** (ni `ip link up/down`, ni wpa_supplicant/NetworkManager propios):
  el chip de Wi-Fi (cnss) se cae. Los servicios D-Bus de wpa_supplicant y bluez están
  enmascarados en la chroot.
- **`am` / `cmd` se cuelgan** con SF frenado (esperan a `system_server`). Congelar apps
  directo por cgroup.
- **Al lanzar desde la app hay que salir de su cgroup** (`echo $$ > /sys/fs/cgroup/cgroup.procs`),
  si no Linux se congela junto con las apps.
- Samsung apaga el touch (`/sys/class/input/inputN/enabled`) cuando "se va" su pantalla:
  hay que re-prenderlo.
- El UID 1000 es `system` en Android: el usuario de Linux usa otro (7777), en los grupos
  `aid_inet` (3003) y `aid_net_raw` (3004) para tener red.
- Después de un cuelgue se pierden escrituras recientes: `sync` después de instalar, y
  borrar `/var/lib/pacman/db.lck` si quedó.

Diagnóstico sin perder la cabeza: `/proc/reset_summary`, `/proc/auto_comment` y
`/proc/last_kmsg` (root) muestran la causa del último reinicio; `dumpsys dropbox` (sin
root) lista `SYSTEM_LAST_KMSG_*_KP/_WP` y `system_server_watchdog`.

## Estructura

```
android/tools/   scripts del lado Android → /data/local/arch-tools/
  archctl          monta la chroot y entra (run/shell)
  native           Android ↔ Linux nativo (el modo principal)
  x11              alternativa: Phosh en una ventana de Termux:X11 (Android usable)
  sftest, stoptest experimentos para ver qué servicio se puede frenar
android/app/     app "Arch" (ícono que corre `native start`), build sin Gradle
android/bridge/  DroidBridge: audio + acelerómetro de Android para Linux (app_process)
chroot/          archivos dentro de la chroot (/usr/local/bin, /etc/phoc, ...)
  mobile-session   sesión: dbus, seatd, fake-logind, phoc
  phosh-start      lo que corre phoc: variables, PipeWire, teclado, Phosh
  fake-logind      logind + iio-sensor-proxy + botón de encendido, en Python
  blackout         capa negra (layer-shell) para la pantalla "apagada"
build/           cómo se compilaron Mesa (Turnip KGSL) y phoc
patches/         wlroots (Vulkan sobre KGSL), phoc (sin DPMS), x11 (experimental, cuelga)
```

## Instalación (resumen)

Requisitos: root temporal con KernelSU (o similar) que dé `su` con contexto sin
restricciones, Android 16 en un S23 SM-S911B. Probado solo en ese equipo.

1. Arch Linux ARM (aarch64) en `/data/local/arch`; usuario de Linux con UID ≠ 1000.
2. Paquetes: `phosh stevia pipewire pipewire-pulse wireplumber upower python-dbus
   python-gobject gtk-layer-shell seatd firefox` (+ las apps que quieras).
3. Compilar Mesa (`build/build-mesa.sh`) y phoc con los parches (`patches/`,
   `build/build-phoc.sh`) dentro de la chroot.
4. Copiar `chroot/` a la chroot y `android/tools/` a `/data/local/arch-tools/`;
   compilar `android/bridge` → `/data/local/arch-tools/bridge.jar`.
5. Una vez: `su -c 'setprop persist.vendor.softdog off'` y reiniciar.
6. `su -c '/data/local/arch-tools/native start'` (o instalar la app de `android/app`).

Fondo de pantalla que usamos: "Sequoia Sunrise" de macOS (no incluido, es de Apple),
recortado vertical con
`magick seq.png -crop 997x2160+1350+0 +repage -resize 1080x2340! sequoia.jpg` →
`/usr/local/share/backgrounds/sequoia.jpg`.

## Riesgos

Esto frena partes de Android y desactiva watchdogs. Si algo sale mal, el teléfono se
cuelga y se reinicia solo (a veces con fsck de `/data`). No toca particiones, pero hacé
backup. Sin garantías.

## Licencia

MIT para el código propio (ver `LICENSE`). Los parches aplican a wlroots (MIT) y phoc
(GPL-3.0); `mobile-config-firefox` es de postmarketOS.
