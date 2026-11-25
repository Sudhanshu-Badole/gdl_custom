"""Phase 2 of Employee Separation: exit questionnaire template, Exit Interview and Employee Separation
custom fields, Employee Nomination workflow and notifications. Idempotent."""

from gdl_custom_app.gdl_hr import setup_phase2


def execute():
	setup_phase2.execute()
