"""A1: embedded raster identities before attempting any new recognition."""
import hashlib
import time
from collections import defaultdict
from common import HERE, ROOT, OLD, F2, SCANS, read, save, sha


def main():
    from pypdf import PdfReader
    start = time.perf_counter()
    docs = read(OLD / "documents.json")
    docs += read(F2 / "dataset_legacy.json")["documents"] + read(F2 / "new_documents.json")
    docs = {d["id"]: d for d in docs if d["id"] in SCANS or
            (d["code"] in ("000961", "000002") and d.get("kind") == "periodic")}
    pages, objects, timings = [], {}, []
    for d in docs.values():
        t = time.perf_counter()
        assert sha(ROOT / d["path"]) == d["sha256"]
        pdf = PdfReader(ROOT / d["path"])
        for n, page in enumerate(pdf.pages, 1):
            images = []

            def walk(resources):
                xobjects = resources.get("/XObject", {})
                for name, ref in xobjects.items():
                    obj = ref.get_object()
                    if obj.get("/Subtype") == "/Form":
                        walk(obj.get("/Resources", {}))
                    if obj.get("/Subtype") != "/Image":
                        continue
                    key = (d["id"], ref.idnum if hasattr(ref, "idnum") else str(name))
                    if key not in objects:
                        raw = obj._data
                        decoded = obj.get_data()
                        descriptor = {"width": obj.get("/Width"), "height": obj.get("/Height"),
                                      "bpc": obj.get("/BitsPerComponent"), "colorspace": str(obj.get("/ColorSpace")),
                                      "filter": str(obj.get("/Filter"))}
                        digest = hashlib.sha256(decoded).hexdigest()
                        objects[key] = {**descriptor, "encoded_sha256": hashlib.sha256(raw).hexdigest(),
                                        "decoded_stream_sha256": digest, "encoded_bytes": len(raw),
                                        "decoded_bytes": len(decoded)}
                    images.append({"name": str(name), **objects[key]})

            walk(page.get("/Resources", {}))
            pages.append({"id": d["id"], "physical_page": n, "mediabox": list(map(float, page.mediabox)),
                          "image_objects": images})
        timings.append({"id": d["id"], "pages": len(pdf.pages), "seconds": time.perf_counter()-t})
        print(timings[-1], flush=True)
    index = defaultdict(list)
    for p in pages:
        for im in p["image_objects"]:
            index[(im["width"], im["height"], im["decoded_stream_sha256"])].append([p["id"], p["physical_page"]])
    matches = []
    for p in pages:
        if p["id"] not in SCANS:
            continue
        large = [im for im in p["image_objects"] if im["width"]*im["height"] > 500000]
        if not large:
            continue
        hits = [v for im in large for v in index[(im["width"], im["height"], im["decoded_stream_sha256"]) ] if v[0] != p["id"]]
        matches.append({"id": p["id"], "physical_page": p["physical_page"], "large_images": len(large),
                        "identical_embedded_image_locations": hits,
                        "identity_level": "IMAGE_OBJECT_ONLY_REQUIRES_PAGE_RENDER_OR_FIELD_VALIDATION"})
    save("image_structure.json", {"documents": list(docs.values()), "pages": pages,
         "scan_large_image_matches": matches, "timings": timings, "seconds": time.perf_counter()-start,
         "new_ocr_runs": 0, "network_requests": 0})
    print({"pages": len(pages), "scan_large_image_pages": len(matches), "with_exact_image_matches": sum(bool(m["identical_embedded_image_locations"]) for m in matches)})


if __name__ == "__main__":
    main()
