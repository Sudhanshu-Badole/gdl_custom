app_name = "gdl_custom_app"
app_title = "Gdl Custom App"
app_publisher = "Sudhanshu Badole"
app_description = "GDL Customization"
app_email = "admin@corenex.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "gdl_custom_app",
# 		"logo": "/assets/gdl_custom_app/logo.png",
# 		"title": "Gdl Custom App",
# 		"route": "/gdl_custom_app",
# 		"has_permission": "gdl_custom_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/gdl_custom_app/css/gdl_custom_app.css"
# app_include_js = "/assets/gdl_custom_app/js/gdl_custom_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/gdl_custom_app/css/gdl_custom_app.css"
# web_include_js = "/assets/gdl_custom_app/js/gdl_custom_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "gdl_custom_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Stock Entry": "public/js/btc_cost_center.js",
	"Sales Invoice": "public/js/btc_cost_center.js",
	"Delivery Note": "public/js/btc_cost_center.js",
	"Purchase Receipt": "public/js/btc_cost_center.js",
	"Stock Reconciliation": "public/js/btc_cost_center.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "gdl_custom_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "gdl_custom_app.utils.jinja_methods",
# 	"filters": "gdl_custom_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "gdl_custom_app.install.before_install"
# after_install = "gdl_custom_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "gdl_custom_app.uninstall.before_uninstall"
# after_uninstall = "gdl_custom_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "gdl_custom_app.utils.before_app_install"
# after_app_install = "gdl_custom_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "gdl_custom_app.utils.before_app_uninstall"
# after_app_uninstall = "gdl_custom_app.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "gdl_custom_app.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "gdl_custom_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"gdl_custom_app.tasks.all"
# 	],
# 	"daily": [
# 		"gdl_custom_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"gdl_custom_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"gdl_custom_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"gdl_custom_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "gdl_custom_app.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "gdl_custom_app.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "gdl_custom_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "gdl_custom_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["gdl_custom_app.utils.before_request"]
# after_request = ["gdl_custom_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["gdl_custom_app.utils.before_job"]
# after_job = ["gdl_custom_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"gdl_custom_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


required_apps = ["frappe", "erpnext"]

# Cost Center auto-fill + BTC stock rules (gdl_custom_app/utils/btc.py). validate,
# so it edits the rows in the same save, before any stock/GL posting.
_btc = "gdl_custom_app.utils.btc.apply_btc_rules_and_cost_centers"
doc_events = {
	"Stock Entry": {
		"validate": [_btc, "gdl_custom_app.utils.fee.validate_fee"],
		"on_submit": "gdl_custom_app.utils.fee.create_fee_issue",
		"on_cancel": "gdl_custom_app.utils.fee.cancel_fee_issue",
	},
	"Sales Invoice": {"validate": _btc},
	"Delivery Note": {"validate": _btc},
	"Purchase Receipt": {"validate": _btc},
	"Stock Reconciliation": {"validate": _btc},
	"Purchase Order": {"validate": "gdl_custom_app.overrides.purchase_order.validate"},
}

override_doctype_class = {"Asset": "gdl_custom_app.overrides.asset.CustomAsset"}

# Zone / Custodian are Inventory Dimensions (they generate the zone/custodian
# fields on every stock doctype); the other fields are plain Custom Fields.
fixtures = [
	{"dt": "Inventory Dimension", "filters": [["name", "in", ["Zone", "Custodian"]]]},
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Warehouse-custom_cost_center",
					"Asset Category-custom_category_code",
				],
			]
		],
	},
	{"dt": "Property Setter", "filters": [["doc_type", "=", "Asset Category"]]},
]
