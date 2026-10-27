"""copy_to_staging: si el buffer no ofrece acceso directo, mapear el DMA-BUF a mano."""
import sys

path = sys.argv[1]
src = open(path).read()
if "map_dmabuf_read" in src:
    print("already patched")
    sys.exit(0)

old_inc = '#include <wlr/render/allocator.h>\n'
new_inc = ('#include <linux/dma-buf.h>\n'
           '#include <sys/ioctl.h>\n'
           '#include <sys/mman.h>\n'
           '#include <wlr/render/allocator.h>\n')

helper_anchor = "// Copia un frame renderizado por la GPU a un buffer SHM (alterna entre dos).\n"
helper = (
    "// Mapea para lectura un DMA-BUF lineal de un solo plano (buffers de Turnip/KGSL).\n"
    "static void *map_dmabuf_read(struct wlr_buffer *buf, size_t *len, size_t *stride,\n"
    "\t\tint *fd) {\n"
    "\tstruct wlr_dmabuf_attributes attribs;\n"
    "\tif (!wlr_buffer_get_dmabuf(buf, &attribs) || attribs.n_planes != 1) {\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\t*fd = attribs.fd[0];\n"
    "\t*stride = attribs.stride[0];\n"
    "\t*len = attribs.offset[0] + (size_t)attribs.stride[0] * attribs.height;\n"
    "\tvoid *data = mmap(NULL, *len, PROT_READ, MAP_SHARED, *fd, 0);\n"
    "\tif (data == MAP_FAILED) {\n"
    "\t\twlr_log_errno(WLR_ERROR, \"mmap DMA-BUF failed\");\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\tstruct dma_buf_sync sync = { .flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };\n"
    "\tioctl(*fd, DMA_BUF_IOCTL_SYNC, &sync);\n"
    "\treturn (char *)data + attribs.offset[0];\n"
    "}\n"
    "\n"
)

old_map = (
    "\tif (!wlr_buffer_begin_data_ptr_access(src, WLR_BUFFER_DATA_PTR_ACCESS_READ,\n"
    "\t\t\t&src_data, &src_fmt, &src_stride)) {\n"
    "\t\twlr_log(WLR_ERROR, \"Failed to map GPU buffer for SHM copy\");\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\tif (!wlr_buffer_begin_data_ptr_access(*dst, WLR_BUFFER_DATA_PTR_ACCESS_WRITE,\n"
    "\t\t\t&dst_data, &dst_fmt, &dst_stride)) {\n"
    "\t\twlr_buffer_end_data_ptr_access(src);\n"
    "\t\treturn NULL;\n"
    "\t}\n"
)
new_map = (
    "\t// Primero acceso directo; si el allocator no lo da, mmap del DMA-BUF.\n"
    "\tbool src_direct = wlr_buffer_begin_data_ptr_access(src,\n"
    "\t\tWLR_BUFFER_DATA_PTR_ACCESS_READ, &src_data, &src_fmt, &src_stride);\n"
    "\tvoid *map = NULL;\n"
    "\tsize_t map_len = 0;\n"
    "\tint map_fd = -1;\n"
    "\tif (!src_direct) {\n"
    "\t\tmap = map_dmabuf_read(src, &map_len, &src_stride, &map_fd);\n"
    "\t\tif (map == NULL) {\n"
    "\t\t\twlr_log(WLR_ERROR, \"Failed to map GPU buffer for SHM copy\");\n"
    "\t\t\treturn NULL;\n"
    "\t\t}\n"
    "\t\tsrc_data = map;\n"
    "\t}\n"
    "\tif (!wlr_buffer_begin_data_ptr_access(*dst, WLR_BUFFER_DATA_PTR_ACCESS_WRITE,\n"
    "\t\t\t&dst_data, &dst_fmt, &dst_stride)) {\n"
    "\t\tsrc_direct = false;\n"
    "\t\tdst_data = NULL;\n"
    "\t}\n"
)

old_tail = (
    "\twlr_buffer_end_data_ptr_access(*dst);\n"
    "\twlr_buffer_end_data_ptr_access(src);\n"
    "\treturn *dst;\n"
)
new_tail = (
    "\twlr_buffer_end_data_ptr_access(*dst);\n"
    "\tif (src_direct) {\n"
    "\t\twlr_buffer_end_data_ptr_access(src);\n"
    "\t} else {\n"
    "\t\tstruct dma_buf_sync sync = { .flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ };\n"
    "\t\tioctl(map_fd, DMA_BUF_IOCTL_SYNC, &sync);\n"
    "\t\tstruct wlr_dmabuf_attributes attribs;\n"
    "\t\twlr_buffer_get_dmabuf(src, &attribs);\n"
    "\t\tmunmap((char *)map - attribs.offset[0], map_len);\n"
    "\t}\n"
    "\treturn *dst;\n"
)

old_copy = (
    "\tsize_t row = (size_t)src->width * 4;\n"
)
new_copy = (
    "\tif (dst_data == NULL) {\n"
    "\t\tif (src_direct) {\n"
    "\t\t\twlr_buffer_end_data_ptr_access(src);\n"
    "\t\t} else {\n"
    "\t\t\tstruct wlr_dmabuf_attributes attribs;\n"
    "\t\t\twlr_buffer_get_dmabuf(src, &attribs);\n"
    "\t\t\tmunmap((char *)map - attribs.offset[0], map_len);\n"
    "\t\t}\n"
    "\t\treturn NULL;\n"
    "\t}\n"
    "\tsize_t row = (size_t)src->width * 4;\n"
)

for old, new in [(old_inc, new_inc), (helper_anchor, helper + helper_anchor),
                 (old_map, new_map), (old_copy, new_copy), (old_tail, new_tail)]:
    assert src.count(old) == 1, f"pattern not found: {old[:50]!r}"
    src = src.replace(old, new)
open(path, "w").write(src)
print("patched")
