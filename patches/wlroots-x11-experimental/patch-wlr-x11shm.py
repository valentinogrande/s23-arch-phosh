"""Backend X11 de wlroots: render por GPU sin DRI3 (Termux:X11).

Con WLR_VK_KGSL y un servidor X sin DRI3 pero con MIT-SHM, el backend acepta buffers
DMA-BUF (los que renderiza Turnip/KGSL) y en cada commit copia el frame a uno de dos
buffers SHM, que son los que se le pasan al servidor X.
"""
import sys

root = sys.argv[1]


def patch(rel, pairs):
    path = f"{root}/{rel}"
    src = open(path).read()
    if "dmabuf_via_shm" in src:
        print(f"{rel}: already patched")
        return
    for old, new in pairs:
        assert src.count(old) == 1, f"{rel}: pattern not found: {old[:60]!r}"
        src = src.replace(old, new)
    open(path, "w").write(src)
    print(f"{rel}: patched")


patch("include/backend/x11.h", [
    ("\tpixman_region32_t exposed;\n",
     "\tpixman_region32_t exposed;\n"
     "\n"
     "\t// dmabuf_via_shm: el frame de la GPU se copia acá antes de mandarlo al X\n"
     "\tstruct wlr_buffer *staging[2];\n"
     "\tint staging_idx;\n"),
    ("\tbool have_shm;\n",
     "\tbool have_shm;\n"
     "\tbool dmabuf_via_shm; // sin DRI3: aceptar DMA-BUF y copiar a SHM\n"
     "\tstruct wlr_allocator *shm_allocator;\n"),
])

patch("backend/x11/backend.c", [
    ("\tconst struct wlr_drm_format *shm_format =\n"
     "\t\twlr_drm_format_set_get(&x11->shm_formats, x11->x11_format->drm);\n"
     "\tif (x11->have_shm && shm_format != NULL) {\n"
     "\t\twlr_drm_format_set_add(&x11->primary_shm_formats,\n"
     "\t\t\tshm_format->format, DRM_FORMAT_MOD_INVALID);\n"
     "\t}\n",
     "\tconst struct wlr_drm_format *shm_format =\n"
     "\t\twlr_drm_format_set_get(&x11->shm_formats, x11->x11_format->drm);\n"
     "\tif (x11->have_shm && shm_format != NULL) {\n"
     "\t\twlr_drm_format_set_add(&x11->primary_shm_formats,\n"
     "\t\t\tshm_format->format, DRM_FORMAT_MOD_INVALID);\n"
     "\t}\n"
     "\n"
     "\t// Termux:X11 no tiene DRI3: con la GPU KGSL renderizamos a DMA-BUF lineal y\n"
     "\t// copiamos cada frame a SHM en output_commit_buffer().\n"
     "\tif (!x11->have_dri3 && x11->have_shm && shm_format != NULL &&\n"
     "\t\t\tgetenv(\"WLR_VK_KGSL\") != NULL) {\n"
     "\t\tx11->dmabuf_via_shm = true;\n"
     "\t\tx11->backend.buffer_caps |= WLR_BUFFER_CAP_DMABUF;\n"
     "\t\twlr_drm_format_set_add(&x11->primary_dri3_formats,\n"
     "\t\t\tshm_format->format, DRM_FORMAT_MOD_LINEAR);\n"
     "\t\twlr_log(WLR_INFO, \"No DRI3: rendering to DMA-BUF and copying to SHM\");\n"
     "\t}\n"),
])

patch("backend/x11/output.c", [
    ('#include "backend/x11.h"\n',
     '#include <wlr/render/allocator.h>\n'
     '\n'
     '#include "backend/x11.h"\n'
     '#include "render/allocator/shm.h"\n'
     '#include "render/drm_format_set.h"\n'),
    ("\tpixman_region32_fini(&output->exposed);\n",
     "\tpixman_region32_fini(&output->exposed);\n"
     "\n"
     "\tfor (size_t i = 0; i < 2; i++) {\n"
     "\t\tif (output->staging[i] != NULL) {\n"
     "\t\t\twlr_buffer_drop(output->staging[i]);\n"
     "\t\t}\n"
     "\t}\n"),
    ("static bool output_commit_buffer(struct wlr_x11_output *output,\n"
     "\t\tconst struct wlr_output_state *state) {\n"
     "\tstruct wlr_x11_backend *x11 = output->x11;\n"
     "\n"
     "\tstruct wlr_buffer *buffer = state->buffer;\n",
     "// Copia un frame renderizado por la GPU a un buffer SHM (alterna entre dos).\n"
     "static struct wlr_buffer *copy_to_staging(struct wlr_x11_output *output,\n"
     "\t\tstruct wlr_buffer *src) {\n"
     "\tstruct wlr_x11_backend *x11 = output->x11;\n"
     "\tif (x11->shm_allocator == NULL) {\n"
     "\t\tx11->shm_allocator = wlr_shm_allocator_create();\n"
     "\t\tif (x11->shm_allocator == NULL) {\n"
     "\t\t\treturn NULL;\n"
     "\t\t}\n"
     "\t}\n"
     "\n"
     "\toutput->staging_idx ^= 1;\n"
     "\tstruct wlr_buffer **dst = &output->staging[output->staging_idx];\n"
     "\tif (*dst != NULL && ((*dst)->width != src->width ||\n"
     "\t\t\t(*dst)->height != src->height)) {\n"
     "\t\twlr_buffer_drop(*dst);\n"
     "\t\t*dst = NULL;\n"
     "\t}\n"
     "\tif (*dst == NULL) {\n"
     "\t\tstruct wlr_drm_format format = {0};\n"
     "\t\tif (!wlr_drm_format_add(&format, DRM_FORMAT_MOD_INVALID)) {\n"
     "\t\t\treturn NULL;\n"
     "\t\t}\n"
     "\t\tformat.format = x11->x11_format->drm;\n"
     "\t\t*dst = wlr_allocator_create_buffer(x11->shm_allocator,\n"
     "\t\t\tsrc->width, src->height, &format);\n"
     "\t\twlr_drm_format_finish(&format);\n"
     "\t\tif (*dst == NULL) {\n"
     "\t\t\treturn NULL;\n"
     "\t\t}\n"
     "\t}\n"
     "\n"
     "\tvoid *src_data, *dst_data;\n"
     "\tuint32_t src_fmt, dst_fmt;\n"
     "\tsize_t src_stride, dst_stride;\n"
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
     "\tsize_t row = (size_t)src->width * 4;\n"
     "\tfor (int y = 0; y < src->height; y++) {\n"
     "\t\tmemcpy((char *)dst_data + y * dst_stride,\n"
     "\t\t\t(const char *)src_data + y * src_stride, row);\n"
     "\t}\n"
     "\twlr_buffer_end_data_ptr_access(*dst);\n"
     "\twlr_buffer_end_data_ptr_access(src);\n"
     "\treturn *dst;\n"
     "}\n"
     "\n"
     "static bool output_commit_buffer(struct wlr_x11_output *output,\n"
     "\t\tconst struct wlr_output_state *state) {\n"
     "\tstruct wlr_x11_backend *x11 = output->x11;\n"
     "\n"
     "\tstruct wlr_buffer *buffer = state->buffer;\n"
     "\tif (x11->dmabuf_via_shm) {\n"
     "\t\tbuffer = copy_to_staging(output, buffer);\n"
     "\t\tif (buffer == NULL) {\n"
     "\t\t\treturn false;\n"
     "\t\t}\n"
     "\t}\n"),
    ("\tif (x11->have_dri3 && (buffer_caps & WLR_BUFFER_CAP_DMABUF)) {\n"
     "\t\treturn &output->x11->primary_dri3_formats;\n",
     "\tif ((x11->have_dri3 || x11->dmabuf_via_shm) &&\n"
     "\t\t\t(buffer_caps & WLR_BUFFER_CAP_DMABUF)) {\n"
     "\t\treturn &output->x11->primary_dri3_formats;\n"),
])
