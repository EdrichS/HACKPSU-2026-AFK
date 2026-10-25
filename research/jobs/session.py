"""One SparkSession for every job: local mode, 4 cores, 2 GB for the driver.

PySpark 4.2 runs on Java 17, 21 or 25. If JAVA_HOME is unset (or empty, which Spark's own scripts
treat the same way) and Java 17 is installed at the usual macOS path, the jobs use it. Otherwise
JAVA_HOME is left as it is, so point it at a supported Java yourself if the default `java` is newer.

The workers run the same Python as the driver (this project's .venv), and corpus_jobs.py is shipped
to them, so the jobs work from any working directory.
"""
import os
import sys
from pathlib import Path

JAVA_17 = "/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home"

if not os.environ.get("JAVA_HOME") and Path(JAVA_17).is_dir():
    os.environ["JAVA_HOME"] = JAVA_17
# PySpark needs the same Python version in the driver and the workers.
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")

from pyspark.sql import SparkSession  # noqa: E402


def spark(app: str) -> SparkSession:
    s = (
        SparkSession.builder.appName(app)
        .master("local[4]")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    s.sparkContext.setLogLevel("ERROR")
    s.sparkContext.addPyFile(str(Path(__file__).with_name("corpus_jobs.py")))
    return s
