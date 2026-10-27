import sys

path = sys.argv[1]
src = open(path).read()
old = "\t\tbuffer = copy_to_staging(output, buffer);\n\t\tif (buffer == NULL) {\n\t\t\tgoto error;"
new = "\t\tbuffer = copy_to_staging(output, buffer);\n\t\tif (buffer == NULL) {\n\t\t\treturn false;"
if new in src:
    print("already fixed")
else:
    assert src.count(old) == 1, "pattern not found"
    open(path, "w").write(src.replace(old, new))
    print("fixed")
