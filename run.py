import os
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
    worker = subprocess.Popen([sys.executable, str(ROOT / "etl_job.py"), "--loop"], cwd=ROOT)
    try:
        raise SystemExit(subprocess.call([
            sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
            "--server.address", "127.0.0.1",
        ], cwd=ROOT, env={**os.environ, "ETL_LOCAL_ADMIN": "1"}))
    finally:
        worker.terminate()
        worker.wait()
