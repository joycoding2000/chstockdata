from download_named import download
from acquire import OUT, read
download(read(OUT/'material_download_plan.json'))
