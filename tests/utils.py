def read_file(filename):
    with open(filename, "r") as f:
        content = f.read()
    return content


def write_file(filename, content):
    with open(filename, "w") as f:
        f.write(content)
