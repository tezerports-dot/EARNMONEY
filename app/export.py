"""Bank-upload exports.

Both formats carry the same five columns a bank bulk-upload sheet expects:
Full Name, Account Number, IFSC, UPI ID, Amount (INR). Rows without bank
details on file are skipped and reported separately, because a bank file with
a blank account number is worse than a short one.
"""

from __future__ import annotations

import csv
import io
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from app import db

COLUMNS = ["Full Name", "Account Number", "IFSC", "UPI ID", "Amount (INR)"]

# A bank file should only ever contain money that is actually approved to move.
EXPORTABLE_STATUSES = ("pending", "approved")


def collect_rows(
    month: str, status: str = "all"
) -> tuple[list[list[str]], list[str]]:
    """Return ``(rows, skipped_uids)`` for one month."""
    statuses: Iterable[str]
    if status in ("all", "", None):
        statuses = EXPORTABLE_STATUSES
    else:
        statuses = (status,)

    rows: list[list[str]] = []
    skipped: list[str] = []
    for record in db.list_withdrawals(month=month):
        if record["status"] not in statuses:
            continue
        if not record["account_number"]:
            skipped.append(str(record["uid"] or record["user_id"]))
            continue
        rows.append(
            [
                str(record["full_name"] or ""),
                str(record["account_number"] or ""),
                str(record["ifsc"] or ""),
                str(record["upi_id"] or ""),
                f"{float(record['amount']):.2f}",
            ]
        )
    return rows, skipped


def to_csv(month: str, status: str = "all") -> tuple[bytes, list[str]]:
    rows, skipped = collect_rows(month, status)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig"), skipped


def to_xlsx(month: str, status: str = "all") -> tuple[bytes, list[str]]:
    rows, skipped = collect_rows(month, status)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"Payouts {month}"

    sheet.append(COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for row in rows:
        sheet.append(row[:4] + [float(row[4])])

    # Account numbers must stay text: Excel would otherwise render a 16-digit
    # number in scientific notation and corrupt the upload.
    for row_index in range(2, sheet.max_row + 1):
        sheet.cell(row=row_index, column=2).number_format = "@"
        sheet.cell(row=row_index, column=5).number_format = "0.00"

    widths = [28, 24, 14, 28, 14]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), skipped


def filename(month: str, status: str, extension: str) -> str:
    tag = status if status and status != "all" else "payable"
    return f"payouts-{month}-{tag}.{extension}"
