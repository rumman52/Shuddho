"""Bounded arithmetic shared by previews, PDF/CSV values, and XLSX caches."""
from decimal import Decimal, localcontext
from functools import reduce
from operator import mul


def checked(value):
    if not value.is_finite() or abs(value) > Decimal("1e15"):
        raise ValueError("A calculated value exceeds the supported range")
    return float(value)


def table_values(draft):
    columns = draft.columns + draft.calculations
    ids = [column.id for column in columns]
    rows = []
    with localcontext() as context:
        context.prec = 50
        for original in draft.rows:
            cells = dict(zip(ids, original))
            for column in draft.calculations:
                values = [cells[key] for key in column.inputs]
                if any(value is None for value in values):
                    result = None
                else:
                    numbers = [Decimal(str(value)) for value in values]
                    if column.operation == "sum":
                        result = sum(numbers)
                    elif column.operation == "difference":
                        result = numbers[0] - numbers[1]
                    elif column.operation == "product":
                        result = reduce(mul, numbers)
                    else:
                        result = numbers[0] / numbers[1] if numbers[1] else None
                    if result is not None:
                        result = checked(result)
                cells[column.id] = result
            rows.append([cells[key] for key in ids])
        totals = []
        for index, column in enumerate(columns):
            values = [row[index] for row in rows]
            # Missing inputs must not become a healthy-looking partial total.
            if column.aggregate == "none" or any(value is None for value in values):
                totals.append(None)
            else:
                total = sum(Decimal(str(value)) for value in values)
                totals.append(checked(total / len(values) if column.aggregate == "average" else total))
    return {"columns": [{"id": c.id, "label": c.label, "format": c.format, "aggregate": c.aggregate,
                         "calculated": i >= len(draft.columns)} for i, c in enumerate(columns)],
            "rows": rows, "totals": totals}


def row_formula(column, addresses):
    refs = [addresses[key] for key in column.inputs]
    op = {"sum": "+", "difference": "-", "product": "*", "ratio": "/"}[column.operation]
    calculation = op.join(refs)
    # COUNT distinguishes blank/text inputs from an actual zero. IFERROR makes
    # undefined division blank, matching the server's None result.
    return f'=IF(COUNT({",".join(refs)})={len(refs)},IFERROR({calculation},""),"")'


def aggregate_formula(column, first, last, count):
    function = "AVERAGE" if column.aggregate == "average" else "SUM"
    return f'=IF(COUNT({first}:{last})={count},{function}({first}:{last}),"")'
