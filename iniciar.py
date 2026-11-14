"""Prepara o ambiente e inicia carga e painel com um comando."""
from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 13):
        raise SystemExit("Use Python 3.13 ou superior para preparar o projeto.")
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")],
                   cwd=root, check=True)
    return subprocess.call([str(python), str(root / "run.py"), *sys.argv[1:]], cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
