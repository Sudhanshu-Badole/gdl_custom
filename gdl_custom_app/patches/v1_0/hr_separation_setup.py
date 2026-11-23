"""Create roles, Separation Types, custom fields, clearance template, workflow and notifications for the
Employee Separation process. Idempotent: re-running rebuilds the template, workflow and notifications."""

from gdl_custom_app.gdl_hr.setup import execute as setup


def execute():
	setup()
