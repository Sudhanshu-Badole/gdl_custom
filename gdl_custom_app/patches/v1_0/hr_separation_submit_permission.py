"""Let HR Manager submit an Employee Separation (HRMS allows only System Manager). Idempotent."""

import frappe

from gdl_custom_app.gdl_hr import setup_phase3


def execute():
	setup_phase3.grant_hr_submit()
	frappe.clear_cache()
