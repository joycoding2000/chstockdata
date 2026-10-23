"""Execute an explicit request list; source URLs are recorded by acquire."""
import json
from pathlib import Path
import sys
from acquire import capture

for label, url in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
    capture(label, url)
