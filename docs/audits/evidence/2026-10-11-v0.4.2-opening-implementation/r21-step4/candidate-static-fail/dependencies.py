"""Public dependency identity, excluding direct URLs and environment secrets."""
import importlib.metadata as metadata
import json
import sys
items = [{"name": d.metadata["Name"], "version": d.version,
          "installation_path": str(d.locate_file(""))} for d in metadata.distributions()]
print(json.dumps({"python": sys.version, "executable": sys.executable,
                  "dependencies": sorted(items, key=lambda x: (x["name"].lower(), x["installation_path"]))}, indent=2))
