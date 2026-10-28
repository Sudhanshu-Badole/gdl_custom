import frappe
from erpnext.assets.doctype.asset.asset import Asset
from frappe.model.naming import make_autoname


class CustomAsset(Asset):
    def autoname(self):
        if not self.asset_category:
            frappe.throw("Please select an Asset Category.")

        category_code = frappe.db.get_value(
            "Asset Category",
            self.asset_category,
            "custom_category_code"
        )

        if not category_code:
            frappe.throw(
                f"Category Code is missing for Asset Category "
                f"{self.asset_category}."
            )

        naming_series = f"GDL/{category_code}/.YY./.#####"
        self.name = make_autoname(naming_series)