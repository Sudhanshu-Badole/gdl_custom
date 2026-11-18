"""Stock Ledger report: show BTC quantities with 8 decimals.

ERPNext's Stock Ledger columns use the system float precision (3), so a movement such as
0.000005 BTC shows as 0.000. When the result contains the BTC item (GDL Setting), the quantity
columns are given precision 8. Other reports and results without BTC are returned unchanged.
"""

import frappe
from frappe.desk.query_report import run as core_run

BTC_QTY_PRECISION = 8
STOCK_LEDGER_QTY_COLUMNS = ("actual_qty", "in_qty", "out_qty", "qty_after_transaction")


@frappe.whitelist()
@frappe.read_only()
def run(
	report_name: str,
	filters: str | dict | None = None,
	user: str | None = None,
	ignore_prepared_report: bool = False,
	custom_columns: str | list | None = None,
	is_tree: bool = False,
	parent_field: str | None = None,
	are_default_filters: bool = True,
	js_filters: str | list | None = None,
) -> dict:
	result = core_run(
		report_name=report_name,
		filters=filters,
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
		js_filters=js_filters,
	)
	if report_name == "Stock Ledger":
		set_btc_qty_precision(result)
	return result


def set_btc_qty_precision(result):
	btc_item = frappe.db.get_single_value("GDL Setting", "btc_item")
	if not btc_item or not isinstance(result, dict):
		return
	rows = result.get("result") or []
	if not any(isinstance(row, dict) and row.get("item_code") == btc_item for row in rows):
		return
	for column in result.get("columns") or []:
		if isinstance(column, dict) and column.get("fieldname") in STOCK_LEDGER_QTY_COLUMNS:
			column["precision"] = BTC_QTY_PRECISION
