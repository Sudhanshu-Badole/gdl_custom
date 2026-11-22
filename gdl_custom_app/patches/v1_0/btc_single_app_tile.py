"""One desk tile for the app, named "Digital Asset Process".

Frappe auto-creates an App icon from `add_to_apps_screen`, labelled with the app title ("Gdl Custom App"),
while the app also shipped its own "BTC Inventory" Link icon: two tiles for the same screen. Keep the App
icon (it has the logo), name it after the new app title, drop the Link icon, and set the sidebar and
workspace titles directly (re-importing the app files does not change records that already exist). Idempotent.
"""

import frappe

LABEL = "Digital Asset Process"
OLD_APP_LABEL = "Gdl Custom App"


def execute():
	if frappe.db.exists("Desktop Icon", "BTC Inventory"):
		frappe.delete_doc("Desktop Icon", "BTC Inventory", force=True, ignore_permissions=True)

	if frappe.db.exists("Desktop Icon", OLD_APP_LABEL) and not frappe.db.exists("Desktop Icon", LABEL):
		frappe.rename_doc("Desktop Icon", OLD_APP_LABEL, LABEL, force=True)
	if frappe.db.exists("Desktop Icon", LABEL):
		frappe.db.set_value("Desktop Icon", LABEL, "label", LABEL, update_modified=False)

	if frappe.db.exists("Workspace Sidebar", "BTC Inventory"):
		frappe.db.set_value("Workspace Sidebar", "BTC Inventory", "title", LABEL, update_modified=False)
	if frappe.db.exists("Workspace", "BTC Inventory"):
		frappe.db.set_value("Workspace", "BTC Inventory", {"label": LABEL, "title": LABEL}, update_modified=False)

	frappe.clear_cache()
