# Third-party material

spark-fleet-updates is MIT licensed (see `LICENSE`). It contains and derives
from material that is not ours:

| what | where | licence |
|---|---|---|
| NVIDIA's OTA release recipes (`spark-ota-*.json`), shipped in the `nvidia-spark-ota-check` package and copied from a node | `spark_fleet/recipes/`, `reference/node-sparky/spark-ota-check/metadata/` | BSD-3-Clause, as the package that ships them |
| `nvidia-spark-ota-check` sources, kept for reference and validation | `reference/node-sparky/spark-ota-check/*.py` | BSD-3-Clause (headers intact) |
| `spark_fleet/otascore.py` is a re-implementation of that scorer's logic in our own code, validated against it | `spark_fleet/otascore.py` | MIT (ours), derived from BSD-3-Clause work |
| NVIDIA's Enterprise Lifecycle Integration Scripts, extracted from the published zip | `reference/nvidia/enterprise-lifecycle-integration-scripts/` | MIT / BSD-3-Clause per file; see its `LICENSE` and `THIRD_PARTY_NOTICES.md` |
| Small configuration files and selected string literals from the `dgx-dashboard` package, quoted for documentation | `reference/node-sparky/dgx-dashboard/`, `reference/node-sparky/etc/`, `reference/node-sparky/apt/` | NVIDIA; reproduced as facts about the system's behaviour |
| Captured command output from three lab nodes (serials redacted) | `reference/observed/`, `reference/collector-inputs/` | ours |

NVIDIA, DGX, DGX Spark and ConnectX are trademarks of NVIDIA Corporation.
This project is not affiliated with or endorsed by NVIDIA or ASUS.
