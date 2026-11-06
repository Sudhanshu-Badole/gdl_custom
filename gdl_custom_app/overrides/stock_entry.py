"""Stock Entry GL for BTC transfer-fee issues.

A fee Material Issue (custom_fee_charge_for set, created by utils/fee.py) is
posted by ERPNext as Dr Fee Expense / Cr BTC stock at weighted-average cost.
Here we add the difference between the fee's market value and that cost:

    market = fee qty x Fee Market Rate (USD) x USD->BTN selling rate
    Dr Fee Expense      market - cost   (ERPNext merges it with the cost line)
    Cr Disposal Gain/Loss market - cost  (sides swap when it is a loss)

so the voucher shows the fee at market value and the gain/loss separately.
"""

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from frappe import _
from frappe.utils import flt


class CustomStockEntry(StockEntry):
	def get_gl_entries(self, inventory_account_map):
		gl_entries = super().get_gl_entries(inventory_account_map)
		if self.get("custom_fee_charge_for"):
			gl_entries.extend(self.get_fee_gain_loss_gl_entries())
		return gl_entries

	def get_fee_gain_loss_gl_entries(self):
		settings = frappe.get_cached_doc("GDL Setting")
		gain_loss_account = settings.disposal_gain_loss_account
		fx_rate = flt(self.get("custom_usd_btn_rate"))
		if not gain_loss_account or not fx_rate:
			return []

		precision = self.get_debit_field_precision()
		entries = []
		for row in self.get("items"):
			market_rate = flt(row.get("custom_issue_fee_rate"))
			if not market_rate or not row.s_warehouse:
				continue

			cost = -flt(
				frappe.db.sql(
					"""select sum(stock_value_difference) from `tabStock Ledger Entry`
					where voucher_type='Stock Entry' and voucher_no=%s and voucher_detail_no=%s and is_cancelled=0""",
					(self.name, row.name),
				)[0][0]
			)
			market = flt(flt(row.transfer_qty or row.qty) * market_rate * fx_rate, precision)
			diff = flt(market - cost, precision)
			if not diff:
				continue

			# gain: Dr fee / Cr gain-loss; loss: the reverse
			debit_account, credit_account = (
				(row.expense_account, gain_loss_account) if diff > 0 else (gain_loss_account, row.expense_account)
			)
			amount = abs(diff)
			remarks = _("Network fee {0} BTC at USD {1} x {2}: market value vs weighted-average cost").format(
				flt(row.transfer_qty or row.qty), market_rate, fx_rate
			)
			for account, against, field in (
				(debit_account, credit_account, "debit"),
				(credit_account, debit_account, "credit"),
			):
				entries.append(
					self.get_gl_dict(
						{
							"account": account,
							"against": against,
							"cost_center": row.cost_center,
							"remarks": remarks,
							field: amount,
							f"{field}_in_account_currency": amount,
						},
						item=row,
					)
				)
		return entries
