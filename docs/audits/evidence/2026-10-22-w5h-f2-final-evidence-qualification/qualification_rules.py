"""Strict field-level predicates; no issuer/announcement/expected-value patches."""
from decimal import Decimal


def equivalent_cell(cell, reference):
    identity = ("field", "period", "scope", "unit", "multiplier")
    if not all(cell.get(k) == reference.get(k) for k in identity):
        return False
    if cell.get("multiplier") != {"元": 1, "万元": 10000, "百万元": 1000000, "亿元": 100000000}.get(cell.get("unit")):
        return False
    if not all(cell.get(k) for k in ("header_verified", "label_verified", "column_verified", "source_bound")):
        return False
    if 'column_map' in cell:
        col=cell.get('column_index',-1)
        if not isinstance(col,int) or not 0<=col<len(cell['column_map']):return False
        actual_column=cell['column_map'][col]
        if any(actual_column.get(k)!=cell.get(k)for k in ('period','scope')):return False
    return Decimal(cell["value_CNY"]) == Decimal(reference["value_CNY"])


def page_equivalent(a, b):
    return bool(a.get("pixel_sha256") and a.get("size") and
                a["pixel_sha256"] == b.get("pixel_sha256") and a["size"] == b.get("size"))


def fingerprint_qualified(rows, issuer_anchor, parent_excluded):
    matches = [r for r in rows if r["matches"] and r["label"] != "OCF"]
    return bool(issuer_anchor and parent_excluded and
                len({r["label"] for r in matches}) >= 5 and len({r["period"] for r in matches}) >= 2)


def conflict_affects_query(conflict, query):
    deps = [{"field": query["field"], "period": query["period"]}, *query.get("required_dependencies", [])]
    return bool(conflict["code"] == query["code"] and conflict["available_on"] <= query["T"] and
                {"field": conflict["field"], "period": conflict["period"]} in deps)
