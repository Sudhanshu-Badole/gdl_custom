"""Nomination status for the separation process (rule 7: a valid nomination, shares total 100%)."""

import frappe
from frappe.utils import flt

MISSING = "Missing"
NOT_VERIFIED = "Not Verified"
TOTAL_WRONG = "Total not 100%"
VALID = "Valid"


def get_nomination_status(employee):
	"""Missing / Not Verified / Total not 100% / Valid. Only a Verified nomination totalling 100% is valid."""
	row = frappe.db.get_value(
		"Employee Nomination", {"employee": employee}, ["workflow_state", "total_share"], as_dict=True
	)
	if not row:
		return MISSING
	if flt(row.total_share, 2) != 100:
		return TOTAL_WRONG
	if row.workflow_state != "Verified":
		return NOT_VERIFIED
	return VALID
