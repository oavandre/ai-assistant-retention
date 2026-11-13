import subprocess
import sys

from etl import DB, ROOT, build

if __name__ == "__main__":
    if "--rebuild" in sys.argv or not DB.is_file():
        try:
            build()
        except Exception as exc:
            raise SystemExit(
                f"Carga interrompida: {exc}\n"
                "Confira o acesso ao Hugging Face ou coloque todos os Parquet em data/raw."
            ) from exc
    raise SystemExit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")
    ], cwd=ROOT))
