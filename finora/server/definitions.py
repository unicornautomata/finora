"""Screen and entity definitions. The server publishes these at /meta, so the PyQt6
client and a future web client render the same screens from the same source.
Table and column names used in SQL only ever come from here (never from requests)."""
from __future__ import annotations


def F(name, label, type="text", required=False, **kw):
    return dict(name=name, label=label, type=type, required=required, **kw)


ROLES = ["viewer", "accountant", "admin"]

ENTITIES = {
    "companies": dict(table="companies", pk="cocd", label="Company", plural="Companies", fields=[
        F("cocd", "Company Code", required=True, pk=True, maxlen=10),
        F("name", "Name", required=True),
        F("currency", "Local Currency", required=True, maxlen=3),
        F("coa", "Chart of Accounts", "ref", required=True, ref="coa"),
        F("tax_id", "Tax ID")]),
    "coa": dict(table="coa", pk="coa", label="Chart of Accounts", plural="Charts of Accounts", fields=[
        F("coa", "Code", required=True, pk=True, maxlen=10), F("description", "Description")]),
    "gl_types": dict(table="gl_types", pk="gltype", label="GL Type", plural="GL Types", fields=[
        F("gltype", "GL Type", required=True, pk=True, maxlen=10), F("description", "Description"),
        F("coa", "Chart of Accounts", "ref", required=True, ref="coa"),
        F("normal_side", "Normal Side", "select", required=True, options=["D", "C"], default="D")]),
    "gl_accounts": dict(table="gl_accounts", pk="glcd", label="GL Account", plural="GL Accounts", fields=[
        F("glcd", "GL Account", required=True, pk=True, maxlen=20), F("description", "Description"),
        F("gltype", "GL Type", "ref", required=True, ref="gl_types"),
        F("active", "Active", "bool", default=1)]),
    "customers": dict(table="partners", pk="code", label="Customer", plural="Customers",
                      fixed={"kind": "customer"}, fields=[
        F("code", "Customer Code", required=True, pk=True, maxlen=20),
        F("name", "Name", required=True),
        F("glcd", "Reconciliation Account", "ref", ref="gl_accounts"),
        F("cocd", "Company", "ref", ref="companies")]),
    "vendors": dict(table="partners", pk="code", label="Vendor", plural="Vendors",
                    fixed={"kind": "vendor"}, fields=[
        F("code", "Vendor Code", required=True, pk=True, maxlen=20),
        F("name", "Name", required=True),
        F("glcd", "Reconciliation Account", "ref", ref="gl_accounts"),
        F("cocd", "Company", "ref", ref="companies")]),
    "doc_types": dict(table="doc_types", pk="doctype", label="Document Type", plural="Document Types", fields=[
        F("doctype", "Type", required=True, pk=True, maxlen=6), F("description", "Description"),
        F("prefix", "Number Prefix", required=True, maxlen=6)]),
    "users": dict(table="users", pk="username", label="User", plural="Users", admin=True,
                  deletable=False, fields=[
        F("username", "Username", required=True, pk=True, maxlen=40), F("full_name", "Full Name"),
        F("role", "Role", "select", required=True, options=ROLES, default="accountant"),
        F("active", "Active", "bool", default=1),
        F("password", "Password", "password", virtual=True)]),
}

DEFAULT_DOC_TYPES = [("PJ", "Purchases Journal", "PJ-"), ("SJ", "Sales Journal", "SJ-"),
                     ("CDJ", "Cash Disbursements Journal", "CD-"), ("CRJ", "Cash Receipts Journal", "CR-"),
                     ("GJ", "General Journal", "GJ-")]

# Same layout as the original journal-entry mock-up: 3 header columns, a line grid, a detail panel.
DOCUMENT = dict(
    header_layout=[
        [F("doc_no", "Document Number", readonly=True), F("doctype", "Document Type", readonly=True),
         F("cocd", "Company Code", "ref", required=True, ref="companies")],
        [F("doc_date", "Document Date", "date", required=True), F("reference", "Reference Number"),
         F("department", "Department")],
        [F("posting_date", "Posting Date", "date", required=True),
         F("entry_date", "Entry Date", "date", readonly=True), F("entered_by", "Entered By", readonly=True)]],
    description_field=F("description", "Description"),
    line_columns=[F("item_no", "Item", "int", readonly=True, width=60),
                  F("glcd", "GL Account", "ref", required=True, ref="gl_accounts", width=220),
                  F("description", "Description", width=260),
                  F("debit", "Debit", "amount", width=130), F("credit", "Credit", "amount", width=130)],
    detail_layout=[
        [F("item_no", "Document Item Number", readonly=True), F("ref_item_no", "Reference Item Number"),
         F("quantity", "Quantity", "qty")],
        [F("doc_date", "Document Date", "date", readonly=True, from_header=True),
         F("preceding_doc", "Preceding Document Number"), F("unit", "Unit")],
        [F("entry_date", "Entry Date", "date", readonly=True, from_header=True),
         F("origin_ref", "Origin Reference Number"), F("amount", "Amount", "amount", readonly=True)]],
    detail_description=F("product_desc", "Product Description"),
)

MENU = [
    dict(group="Journals", items=[
        dict(key="doc:PJ", label="Purchases Journal"), dict(key="doc:SJ", label="Sales Journal"),
        dict(key="doc:CDJ", label="CDJ"), dict(key="doc:CRJ", label="CRJ"),
        dict(key="doc:GJ", label="Gen Journal")]),
    dict(group="Operations", planned=[
        "Sales Orders", "Lot Numbers", "Material BOMs", "Prdn Orders", "Quality Inspection",
        "Purchase Reqs", "Purchase Orders", "Ship Orders", "Delivery Orders", "WBS", "Projects"]),
    dict(group="Finance", items=[dict(key="report:trial_balance", label="Trial Balance")],
         planned=["Bank Recon", "Dashboard", "Assets", "Banks", "Reports"]),
    dict(group="Master Data", items=[
        dict(key="master:companies", label="Companies"), dict(key="master:coa", label="Chart of Accounts"),
        dict(key="master:gl_types", label="GL Types"), dict(key="master:gl_accounts", label="GL Accounts"),
        dict(key="master:customers", label="Customers"), dict(key="master:vendors", label="Vendors"),
        dict(key="master:doc_types", label="Document Types")],
         planned=["Plants/WHS/Bins", "Depts/Branches", "Products/Matls"]),
    dict(group="Administration", admin=True, items=[dict(key="master:users", label="Users")]),
]
