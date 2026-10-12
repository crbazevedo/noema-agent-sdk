"""Deterministic CSV reconciliation. No scenario names, model calls or SDK effects."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext

FIELDS = ("event_id", "region", "occurred_at", "ingested_at", "amount")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def instant(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)


def parse(data, filename):
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(FIELDS)
            or set(reader.fieldnames) != set(FIELDS)
        ):
            raise ValueError("CSV must contain exactly " + ",".join(FIELDS))
        rows = []
        seen = set()
        for index, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError("malformed row width")
            if not row["event_id"] or row["event_id"] in seen:
                raise ValueError("missing or duplicate event_id")
            seen.add(row["event_id"])
            if index > 10001:
                raise ValueError("report exceeds 10000 records")
            if len(row["amount"]) > 64:
                raise ValueError("amount representation exceeds64 characters")
            amount = Decimal(row["amount"])
            if not amount.is_finite():
                raise ValueError("amount must be finite")
            if amount.copy_abs() > Decimal("1000000000000") or amount.as_tuple().exponent < -4:
                raise ValueError("amount outside supported magnitude1e12 or scale4")
            occurred, ingested = (
                instant(row["occurred_at"]),
                instant(row["ingested_at"]),
            )
            if ingested < occurred:
                raise ValueError("ingestion precedes occurrence")
            rows.append(
                {
                    **row,
                    "record_index": index,
                    "filename": filename,
                    "file_sha256": sha(data),
                    "_amount": amount,
                    "_occurred": occurred,
                    "_ingested": ingested,
                }
            )
        return rows
    except (UnicodeError, csv.Error, InvalidOperation) as error:
        raise ValueError("malformed CSV: " + str(error)) from error


def reconcile(file_bytes, *, window_start, window_end, region, bases):
    start, end = instant(window_start), instant(window_end)
    if end <= start:
        raise ValueError("window end must be after start")
    names = sorted(file_bytes)
    if len(names) != 2:
        raise ValueError("exactly two reports are supported")
    occurrence = [name for name in names if bases.get(name) == "occurred_at"]
    ingestion = [name for name in names if bases.get(name) == "ingested_at"]
    if len(occurrence) == len(ingestion) == 1:
        names = [occurrence[0], ingestion[0]]
    rows = {
        name: [r for r in parse(file_bytes[name], name) if region is None or r["region"] == region]
        for name in names
    }
    a, b = names
    byid = {name: {r["event_id"]: r for r in rows[name]} for name in names}
    aid, bid = set(byid[a]), set(byid[b])
    common = aid & bid
    conflicts = sorted(
        i
        for i in common
        if any(
            byid[a][i][f] != byid[b][i][f] for f in ["region", "_occurred", "_ingested", "_amount"]
        )
    )
    warnings = []
    for name in names:
        basis = bases.get(name)
        if basis not in {"occurred_at", "ingested_at"}:
            warnings.append(f"{name}: unknown time basis")
            continue
        key = "_occurred" if basis == "occurred_at" else "_ingested"
        if any(not (start <= r[key] < end) for r in rows[name]):
            warnings.append(f"{name}: records outside declared {basis} window")
    aonly = sorted(aid - bid)
    bonly = sorted(bid - aid)
    late = [
        i
        for i in aonly
        if start <= byid[a][i]["_occurred"] < end and byid[a][i]["_ingested"] >= end
    ]
    carry = [
        i
        for i in bonly
        if byid[b][i]["_occurred"] < start and start <= byid[b][i]["_ingested"] < end
    ]
    explained = (
        bases.get(a) == "occurred_at"
        and bases.get(b) == "ingested_at"
        and set(late) == set(aonly)
        and set(carry) == set(bonly)
    )
    if not explained:
        warnings.append(
            "Available records do not fully explain the discrepancy by the declared cutoffs"
        )
    if conflicts:
        warnings.append(
            "The same event has conflicting fields across the two files: " + ", ".join(conflicts)
        )
    # Bounds: <=10000 rows *1e12, scale<=4; each total <=1e16 and delta <=2e16.
    # Fixed precision32 safely exceeds the22 significant digits needed for the delta.
    with localcontext() as context:
        context.prec = 32
        totals = {name: sum((r["_amount"] for r in rows[name]), Decimal(0)) for name in names}
        difference = totals[a] - totals[b]
    metrics = {
        "report_a": a,
        "report_b": b,
        "a_rows": len(rows[a]),
        "b_rows": len(rows[b]),
        "a_total": str(totals[a]),
        "b_total": str(totals[b]),
        "difference_a_minus_b": str(difference),
        "common_ids": sorted(common),
        "a_only_ids": aonly,
        "b_only_ids": bonly,
        "late_current_ids": late,
        "carry_in_ids": carry,
        "unresolved_ids": conflicts,
        "warnings": warnings,
    }
    derived = io.StringIO(newline="")
    fields = [
        *FIELDS,
        "source_file",
        "source_record",
        "source_sha256",
        "membership",
        "conflicting",
    ]
    writer = csv.DictWriter(derived, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name in names:
        for r in rows[name]:
            writer.writerow(
                {
                    **{f: r[f] for f in FIELDS},
                    "source_file": name,
                    "source_record": r["record_index"],
                    "source_sha256": r["file_sha256"],
                    "membership": "common"
                    if r["event_id"] in common
                    else ("a_only" if name == a else "b_only"),
                    "conflicting": str(r["event_id"] in conflicts).lower(),
                }
            )
    return {
        "status": "partial" if warnings else "reconciled",
        "metrics": metrics,
        "sources": [
            {
                "file": name,
                "sha256": sha(file_bytes[name]),
                "bytes": len(file_bytes[name]),
                "basis": bases.get(name),
            }
            for name in names
        ],
        "scope": {
            "window_start": window_start,
            "window_end": window_end,
            "interval": "[start,end)",
            "region": region,
        },
        "derived_csv": derived.getvalue(),
    }


def render_note(result, goal_revision):
    m = result["metrics"]
    scope = result["scope"]
    text = [
        f"# Evidence reconciliation ({result['status']})",
        "",
        f"Goal revision: {goal_revision}",
        f"Scope: {scope['region'] or 'all regions'}; {scope['window_start']} ≤ timestamp < {scope['window_end']} (UTC-normalized).",  # noqa: E501 - preserve frozen fixture/event text
        "",
        f"{m['report_a']}: {m['a_rows']} supplied records, amount {m['a_total']}.",
        f"{m['report_b']}: {m['b_rows']} supplied records, amount {m['b_total']}.",
        f"Observed difference A − B: {m['difference_a_minus_b']}.",
        "Late current-period events absent from ingestion-window report: "
        + (", ".join(m["late_current_ids"]) or "none")
        + ".",
        "Prior-period events ingested inside the window: "
        + (", ".join(m["carry_in_ids"]) or "none")
        + ".",
        "",
    ]
    if result["status"] == "partial":
        text += ["## Unresolved / partial", *["- " + w for w in m["warnings"]], ""]
    else:
        text += [
            "The supplied-record discrepancy is consistent with occurrence-date versus ingestion-date cutoffs.",  # noqa: E501 - preserve frozen fixture/event text
            "",
        ]
    text += [
        "This does not establish completeness beyond the supplied files or any causal change in the underlying business.",  # noqa: E501 - preserve frozen fixture/event text
        "",
        "## Sources and calculation rows",
        *[
            "- " + s["file"] + "; SHA-256 " + s["sha256"] + "; basis " + str(s["basis"])
            for s in result["sources"]
        ],
        "See derived.csv: every calculation record carries source filename, source record index, and source-file hash.",  # noqa: E501 - preserve frozen fixture/event text
        "",
    ]
    return "\n".join(text).encode()
