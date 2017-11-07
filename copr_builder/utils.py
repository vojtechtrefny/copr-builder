import subprocess


def run_command(command, cwd=None):
    res = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, cwd=cwd)

    out, err = res.communicate()
    if res.returncode != 0:
        output = out.decode().strip() + '\n' + err.decode().strip()
    else:
        output = out.decode().strip()
    return (res.returncode, output)
