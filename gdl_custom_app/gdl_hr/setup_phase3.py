"""Idempotent setup for Phase 3: Full and Final Statement custom fields, the starting list of benefit and
recovery types (inactive until HR confirms the formulas), Finance read access, the notification to Finance and
the A-F print format. Run from the hr_fnf_setup patch."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission

from gdl_custom_app.gdl_hr.fnf import (
	SECTION_BENEFITS,
	SECTION_EARNED,
	SECTION_RECOVERIES,
)

FNF = "Full and Final Statement"
PRINT_FORMAT = "GDL Full and Final Statement"
NOTIFICATION = "Full and Final Statement - Submitted"
FINANCE_ROLES = ("Accounts Manager", "Accounts User")

CUSTOM_FIELDS = {
	FNF: [
		{"fieldname": "custom_process_section", "label": "Separation Process", "fieldtype": "Section Break", "insert_after": "total_asset_recovery_cost"},
		{"fieldname": "custom_separation_request", "label": "Separation Request", "fieldtype": "Link", "options": "Separation Request", "read_only": 1, "no_copy": 1, "insert_after": "custom_process_section"},
		{"fieldname": "custom_separation_type", "label": "Separation Type", "fieldtype": "Link", "options": "Separation Type", "read_only": 1, "insert_after": "custom_separation_request"},
		{"fieldname": "custom_employee_separation", "label": "Employee Separation", "fieldtype": "Link", "options": "Employee Separation", "read_only": 1, "no_copy": 1, "insert_after": "custom_separation_type"},
		{"fieldname": "custom_process_column", "fieldtype": "Column Break", "insert_after": "custom_employee_separation"},
		{"fieldname": "custom_exit_interview", "label": "Exit Interview", "fieldtype": "Link", "options": "Exit Interview", "read_only": 1, "no_copy": 1, "insert_after": "custom_process_column"},
		{"fieldname": "custom_nomination_status", "label": "Nomination Status", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_exit_interview"},
		{"fieldname": "custom_nomination_reason", "label": "Reason to Proceed Without a Valid Nomination", "fieldtype": "Small Text", "insert_after": "custom_nomination_status"},
		{"fieldname": "custom_notice_shortfall_days", "label": "Notice Shortfall (days)", "fieldtype": "Float", "read_only": 1, "insert_after": "custom_nomination_reason", "description": "Shown for reference. Enter the recovery in Section C."},
		{"fieldname": "custom_settlement_section", "label": "Statement Summary", "fieldtype": "Section Break", "insert_after": "custom_notice_shortfall_days"},
		{"fieldname": "custom_total_earned", "label": "A. Earned Pay", "fieldtype": "Currency", "read_only": 1, "insert_after": "custom_settlement_section"},
		{"fieldname": "custom_total_benefits", "label": "B. Separation Benefits", "fieldtype": "Currency", "read_only": 1, "insert_after": "custom_total_earned"},
		{"fieldname": "custom_summary_column", "fieldtype": "Column Break", "insert_after": "custom_total_benefits"},
		{"fieldname": "custom_total_recoveries", "label": "C. Recoveries", "fieldtype": "Currency", "read_only": 1, "insert_after": "custom_summary_column"},
		{"fieldname": "custom_net_payable", "label": "E. Net Payable", "fieldtype": "Currency", "read_only": 1, "bold": 1, "insert_after": "custom_total_recoveries", "description": "A + B less C. A negative figure is recovered from the employee."},
		{"fieldname": "custom_information_section", "label": "For Information (Sections D and F)", "fieldtype": "Section Break", "insert_after": "custom_net_payable"},
		{"fieldname": "custom_information_items", "label": "Information Items", "fieldtype": "Table", "options": "Separation Information Item", "insert_after": "custom_information_section", "description": "Not part of the totals."},
		{"fieldname": "custom_payee_section", "label": "Payees", "fieldtype": "Section Break", "insert_after": "custom_information_items"},
		{"fieldname": "custom_payees", "label": "Payees", "fieldtype": "Table", "options": "Separation Payee", "read_only": 1, "insert_after": "custom_payee_section"},
	],
	"Full and Final Outstanding Statement": [
		{"fieldname": "custom_section", "label": "Section", "fieldtype": "Select", "options": f"\n{SECTION_EARNED}\n{SECTION_BENEFITS}\n{SECTION_RECOVERIES}", "in_list_view": 1, "insert_after": "component", "columns": 2},
		{"fieldname": "custom_benefit_type", "label": "Benefit Type", "fieldtype": "Link", "options": "Separation Benefit Type", "read_only": 1, "no_copy": 1, "insert_after": "custom_section"},
		{"fieldname": "custom_clause_reference", "label": "Clause Reference", "fieldtype": "Data", "insert_after": "remark"},
		{"fieldname": "custom_attachment", "label": "Supporting Document", "fieldtype": "Attach", "insert_after": "custom_clause_reference"},
	],
	"Employee": [
		{"fieldname": "custom_bond_amount", "label": "Training Bond Amount", "fieldtype": "Currency", "insert_after": "custom_training_study_undertaking", "description": "Amount recoverable if the employee leaves before the bond ends."},
		{"fieldname": "custom_bond_start_date", "label": "Bond Start Date", "fieldtype": "Date", "insert_after": "custom_bond_amount"},
		{"fieldname": "custom_bond_end_date", "label": "Bond End Date", "fieldtype": "Date", "insert_after": "custom_bond_start_date"},
	],
}

# (name, section, clause) - created inactive with a zero formula. HR sets the formula and activates it.
BENEFIT_TYPES = (
	("Pro-rated Annual Leave Payment", SECTION_EARNED, "Annual leave payment pro-rated to the last working day"),
	("Pro-rated PBVP", SECTION_EARNED, "Performance based variable pay for the period served"),
	("Gratuity", SECTION_BENEFITS, "Service Rules: gratuity"),
	("Repatriation Allowance", SECTION_BENEFITS, "Service Rules: repatriation allowance"),
	("Transfer Grant", SECTION_BENEFITS, "Service Rules: transfer grant"),
	("Carriage Charge", SECTION_BENEFITS, "Service Rules: carriage charge"),
	("Retrenchment Additional 2 Months TFMR", SECTION_BENEFITS, "Retrenchment: two additional months TFMR"),
	("Pay in Lieu Received from GDL", SECTION_BENEFITS, "Pay in lieu of notice received from GDL"),
	("Cremation and Medical (Demise on Duty)", SECTION_BENEFITS, "Demise on duty"),
	("Notice Shortfall Recovery", SECTION_RECOVERIES, "Pay in lieu of the notice not served"),
	("STTP Bond Refund", SECTION_RECOVERIES, "Short-term training bond"),
	("LTTP Refund", SECTION_RECOVERIES, "Long-term training refund"),
	("Excess or Irregular Payment", SECTION_RECOVERIES, "Excess or irregular payment recovered"),
	("Earned Leave Taken in Advance", SECTION_RECOVERIES, "Earned leave taken in advance"),
	("Other Recovery", SECTION_RECOVERIES, "Any other recovery"),
)

PRINT_HTML = """
<style>
	.fnf h3 { margin: 18px 0 6px; font-size: 14px; }
	.fnf table { width: 100%; border-collapse: collapse; }
	.fnf th, .fnf td { border: 1px solid #999; padding: 4px 8px; font-size: 12px; }
	.fnf td.amt, .fnf th.amt { text-align: right; width: 140px; }
	.fnf tr.total td { font-weight: bold; background: #f3f3f3; }
</style>
<div class="fnf">
<h2 style="text-align:center">GreenDigital Limited<br>Full and Final Settlement Statement</h2>
<table>
	<tr><td><b>Employee</b></td><td>{{ doc.employee }} - {{ doc.employee_name }}</td><td><b>Designation</b></td><td>{{ doc.designation or "" }}</td></tr>
	<tr><td><b>Date of Joining</b></td><td>{{ frappe.format(doc.date_of_joining, {"fieldtype": "Date"}) }}</td><td><b>Relieving Date</b></td><td>{{ frappe.format(doc.relieving_date, {"fieldtype": "Date"}) }}</td></tr>
	<tr><td><b>Separation Type</b></td><td>{{ doc.custom_separation_type or "" }}</td><td><b>Statement Date</b></td><td>{{ frappe.format(doc.transaction_date, {"fieldtype": "Date"}) }}</td></tr>
</table>

{% macro section(title, table, key) %}
<h3>{{ title }}</h3>
<table>
	<tr><th>Item</th><th>Reference</th><th class="amt">Amount</th></tr>
	{% set ns = namespace(total=0) %}
	{% for row in doc.get(table) if row.custom_section == key %}
	<tr><td>{{ row.component }}</td><td>{{ row.custom_clause_reference or row.remark or "" }}</td><td class="amt">{{ frappe.format(row.amount, {"fieldtype": "Currency"}) }}</td></tr>
	{% set ns.total = ns.total + (row.amount or 0) %}
	{% else %}
	<tr><td colspan="3">None</td></tr>
	{% endfor %}
	{% if key == "C. Recoveries" %}
	{% for a in doc.assets_allocated if a.action == "Recover Cost" %}
	<tr><td>Asset not returned: {{ a.asset_name }}</td><td>{{ a.reference or "" }}</td><td class="amt">{{ frappe.format(a.cost, {"fieldtype": "Currency"}) }}</td></tr>
	{% set ns.total = ns.total + (a.cost or 0) %}
	{% endfor %}
	{% endif %}
	<tr class="total"><td colspan="2">Total {{ key }}</td><td class="amt">{{ frappe.format(ns.total, {"fieldtype": "Currency"}) }}</td></tr>
</table>
{% endmacro %}

{{ section("A. Earned Pay", "payables", "A. Earned Pay") }}
{{ section("B. Separation Benefits", "payables", "B. Separation Benefits") }}
{{ section("C. Recoveries", "receivables", "C. Recoveries") }}

{% macro info(title, key) %}
<h3>{{ title }}</h3>
<table>
	<tr><th>Item</th><th class="amt">Amount</th></tr>
	{% for row in doc.custom_information_items if row.section == key %}
	<tr><td>{{ row.description }}</td><td class="amt">{{ frappe.format(row.amount, {"fieldtype": "Currency"}) }}</td></tr>
	{% else %}
	<tr><td colspan="2">None</td></tr>
	{% endfor %}
</table>
{% endmacro %}

{{ info("D. Statutory Deductions (already taken in the final salary slip)", "D. Statutory Deductions") }}

<h3>E. Net Payable</h3>
<table>
	<tr><td>A. Earned Pay</td><td class="amt">{{ frappe.format(doc.custom_total_earned, {"fieldtype": "Currency"}) }}</td></tr>
	<tr><td>B. Separation Benefits</td><td class="amt">{{ frappe.format(doc.custom_total_benefits, {"fieldtype": "Currency"}) }}</td></tr>
	<tr><td>Less C. Recoveries</td><td class="amt">{{ frappe.format(doc.custom_total_recoveries, {"fieldtype": "Currency"}) }}</td></tr>
	<tr class="total"><td>Net Payable</td><td class="amt">{{ frappe.format(doc.custom_net_payable, {"fieldtype": "Currency"}) }}</td></tr>
</table>

<h3>Payees</h3>
<table>
	<tr><th>Payee</th><th>Relationship</th><th class="amt">Share %</th><th class="amt">Amount</th></tr>
	{% for p in doc.custom_payees %}
	<tr><td>{{ p.nominee_name }}</td><td>{{ p.relationship or "" }}</td><td class="amt">{{ p.share_percent }}</td><td class="amt">{{ frappe.format(p.amount, {"fieldtype": "Currency"}) }}</td></tr>
	{% endfor %}
</table>

{{ info("F. Paid Outside GDL (for information only, such as NPPF pension, provident fund and GIS)", "F. Paid Outside GDL") }}

<br><br>
<table style="border:0"><tr>
	<td style="border:0">Prepared by (HR)</td><td style="border:0">Verified by (Finance)</td><td style="border:0">Approved by (Competent Authority)</td>
</tr></table>
</div>
"""


def execute():
	frappe.db.commit()  # custom fields reload meta; the new doctypes must exist first
	create_custom_fields(CUSTOM_FIELDS, update=True)
	create_benefit_types()
	grant_finance_access()
	create_print_format()
	create_notification()
	frappe.clear_cache()


def create_benefit_types():
	for name, section, clause in BENEFIT_TYPES:
		if frappe.db.exists("Separation Benefit Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Separation Benefit Type",
				"benefit_name": name,
				"section": section,
				"formula": "0",
				"is_active": 0,
				"description": clause,
			}
		).insert(ignore_permissions=True)


def grant_finance_access():
	"""Finance reads the statement and builds the journal entry through fnf.create_journal_entry.
	They cannot create, edit, submit or cancel a statement: that stays with HR."""
	for role in FINANCE_ROLES:
		if not frappe.db.exists("Custom DocPerm", {"parent": FNF, "role": role, "permlevel": 0}):
			add_permission(FNF, role, 0)
		frappe.db.set_value(
			"Custom DocPerm", {"parent": FNF, "role": role, "permlevel": 0}, {"read": 1, "write": 0, "export": 1, "report": 1, "print": 1}
		)


def create_print_format():
	doc = frappe.get_doc("Print Format", PRINT_FORMAT) if frappe.db.exists("Print Format", PRINT_FORMAT) else frappe.new_doc("Print Format")
	doc.update(
		{
			"name": PRINT_FORMAT,
			"doc_type": FNF,
			"module": "GDL HR",
			"standard": "No",
			"custom_format": 1,
			"print_format_type": "Jinja",
			"html": PRINT_HTML,
			"disabled": 0,
		}
	)
	doc.save(ignore_permissions=True)


def create_notification():
	doc = frappe.get_doc("Notification", NOTIFICATION) if frappe.db.exists("Notification", NOTIFICATION) else frappe.new_doc("Notification")
	doc.name = NOTIFICATION
	doc.update(
		{
			"subject": "Full and Final Statement {{ doc.name }} is ready for payment",
			"document_type": FNF,
			"event": "Submit",
			"channel": "Email",
			"enabled": 1,
			"message": (
				"<p>HR has submitted the Full and Final Statement for {{ doc.employee_name }}. "
				"Net payable: {{ frappe.format(doc.custom_net_payable, {'fieldtype': 'Currency'}) }}.</p>"
				'<p><a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">{{ doc.name }}</a></p>'
			),
		}
	)
	doc.set("recipients", [])
	for role in ("Accounts Manager",):
		doc.append("recipients", {"receiver_by_role": role})
	doc.save(ignore_permissions=True)
