"""Cluster and test environment configuration."""
import os
from pathlib import Path


CLUSTER_ERA = os.environ.get("CLUSTER_ERA") or ""
if CLUSTER_ERA not in ("", "mary"):
    raise RuntimeError(f"Invalid CLUSTER_ERA: {CLUSTER_ERA}")

TX_ERA = os.environ.get("TX_ERA") or ""
if TX_ERA not in ("", "shelley", "allegra", "mary"):
    raise RuntimeError(f"Invalid TX_ERA: {TX_ERA}")

CLUSTERS_COUNT = os.environ.get("CLUSTERS_COUNT") or 0

BOOTSTRAP_DIR = os.environ.get("BOOTSTRAP_DIR") or ""

NOPOOLS = bool(os.environ.get("NOPOOLS"))

HAS_DBSYNC = bool(os.environ.get("DBSYNC_REPO"))

DONT_OVERWRITE_OUTFILES = bool(os.environ.get("DONT_OVERWRITE_OUTFILES"))

if BOOTSTRAP_DIR and NOPOOLS:
    TESTNET_SCRIPTS_DIR = "testnets_nopools"
elif BOOTSTRAP_DIR:
    TESTNET_SCRIPTS_DIR = "testnets"
else:
    TESTNET_SCRIPTS_DIR = ""

SCRIPTS_DIR = (
    Path(__file__).parent.parent
    / "cluster_scripts"
    / (TESTNET_SCRIPTS_DIR or CLUSTER_ERA or "mary")
)
