set -e
pacman -S --noconfirm --needed python-mako python-yaml python-packaging python-pyelftools bison flex glslang spirv-tools libdrm wayland wayland-protocols libelf zstd > /root/mesa-deps.log 2>&1
cd /root
[ -d mesa ] || git clone -q --depth 1 --branch mesa-26.2.5 https://gitlab.freedesktop.org/mesa/mesa.git
cd mesa
rm -rf _build
meson setup _build --prefix=/opt/mesa-kgsl --buildtype=release \
    -Dvulkan-drivers=freedreno -Dfreedreno-kmds=kgsl \
    -Dgallium-drivers=zink -Dplatforms=wayland \
    -Dglx=disabled -Dllvm=disabled -Dgbm=disabled -Degl=enabled -Dgles2=enabled \
    -Dvideo-codecs= -Dvulkan-layers= -Dtools= > /root/mesa-setup.log 2>&1 || { tail -30 /root/mesa-setup.log; exit 1; }
ninja -C _build > /root/mesa-build.log 2>&1 || { tail -30 /root/mesa-build.log; exit 1; }
ninja -C _build install > /root/mesa-install.log 2>&1
ls /opt/mesa-kgsl/share/vulkan/icd.d/
echo MESA-OK
