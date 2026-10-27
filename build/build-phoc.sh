cd /root/phoc
meson setup _build --prefix=/usr/local --buildtype=release -Dembed-wlroots=enabled --default-library=static -Dtests=false -Dman=false -Dgtk_doc=false --wrap-mode=default > /root/phoc-setup.log 2>&1 || { tail -30 /root/phoc-setup.log; exit 1; }
ninja -C _build > /root/phoc-build.log 2>&1 || { tail -30 /root/phoc-build.log; exit 1; }
ninja -C _build install > /root/phoc-install.log 2>&1 || { tail -30 /root/phoc-install.log; exit 1; }
ldd /usr/local/bin/phoc | grep -c wlroots
echo BUILD-OK
