# tkinter_app_enhanced.py
"""
Supermarket Management & Billing System (single-file, pure tkinter)
Enhanced Version: Added 'Stock Analytics Graph'.

Features:
- Login: username 'python' / password 'python' (manager)
- Billing page:
    - Left: product list lines: "Name (Barcode: CODE) - ₹price - Stock: N" with [+] add button
    - Barcode input to add by code
    - Right: billing tree (grouped), subtotal/tax/total, Clear/Remove/Edit, Customer, Generate PDF receipt
    - On checkout: backend stock decreases, stock_history recorded, low-stock detection & email alerts
- Stock Dashboard:
    - Top: low-stock warning text listing items under threshold
    - Below: inventory table (ID, Name, Category, Price, Stock, Barcode) with red highlight
- Analytics Tab:
    - Graphs showing stock history vs time using Matplotlib.
- PDF: Neat simple formatted PDF via reportlab (if installed), else fallback to text
- Email alert: SMTP via Gmail using EMAIL_USER and EMAIL_PASS
- Database: sqlite3 'supermarket.db' auto-created and seeded
"""

import os
import sqlite3
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


# Try to use reportlab for nicer PDF receipts
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# Try to use matplotlib for graphs
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# ---------- Configuration ----------
DB_FILE = "supermarket.db"
LOW_STOCK_THRESHOLD = 10
DEFAULT_TAX_PERCENT = 0.0  # kept zero as requested
# Email credentials (hardcoded per your request)
EMAIL_USER = "sanjanahv6@gmail.com"
EMAIL_PASS = "fcsn hais snwz pwiu"  # Replace with actual app password for real emailing

# Single login
DEFAULT_USERNAME = "python"
DEFAULT_PASSWORD = "python"
DEFAULT_ROLE = "manager"

# ---------- Database helpers ----------
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT,
                    role TEXT
                 )''')
    # Inventory table
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    barcode TEXT UNIQUE,
                    name TEXT,
                    category TEXT,
                    price REAL,
                    quantity INTEGER,
                    created_at TEXT
                 )''')
    # Sales table
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_date TEXT,
                    items_json TEXT,
                    total_amount REAL,
                    customer_name TEXT
                 )''')
    # Stock history table
    c.execute('''CREATE TABLE IF NOT EXISTS stock_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    record_date TEXT,
                    quantity INTEGER
                 )''')
    # add single default user if none
    c.execute("SELECT COUNT(*) AS cnt FROM users")
    if c.fetchone()["cnt"] == 0:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  (DEFAULT_USERNAME, DEFAULT_PASSWORD, DEFAULT_ROLE))
    # seed inventory if empty
    c.execute("SELECT COUNT(*) AS cnt FROM inventory")
    if c.fetchone()["cnt"] == 0:
        seed_default_items(c)
    conn.commit()
    conn.close()

def seed_default_items(cursor):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    defaults = [
        ("MILK500", "Milk 500ml", "Dairy", 30.00, 20),
        ("BREAD01", "Bread (400g)", "Bakery", 40.00, 20),
        ("PARLEG1", "Parle-G (100g)", "Snacks", 10.00, 20),
        ("SUGAR1", "Sugar 1kg", "Grocery", 45.00, 20),
        ("RICE1KG", "Rice 1kg", "Grocery", 70.00, 20),
        ("ATTA1KG", "Atta/Flour 1kg", "Grocery", 55.00, 20),
        ("PANEER2", "Paneer 200g", "Dairy", 75.00, 20),
        ("CHEESE1", "Cheese Slice Pack", "Dairy", 120.00, 20),
        ("DAIRYM", "Dairy Milk 65g", "Snacks", 20.00, 20),
        ("LAYS50", "Lays Chips 50g", "Snacks", 20.00, 20),
        ("KITKAT", "KitKat 2-finger", "Snacks", 25.00, 20),
        ("SHAMPOO_S", "Shampoo Sachet", "Personal Care", 5.00, 50),
        ("SHAMPOO_B", "Shampoo Bottle 200ml", "Personal Care", 95.00, 20),
        ("SOAP001", "Soap (Lux)", "Personal Care", 35.00, 20),
        ("BAGPLST", "Plastic Carry Bag", "General", 5.00, 100)
    ]
    for barcode, name, cat, price, qty in defaults:
        cursor.execute('''INSERT OR IGNORE INTO inventory (barcode, name, category, price, quantity, created_at)
                          VALUES (?, ?, ?, ?, ?, ?)''', (barcode, name, cat, price, qty, now))
        # Initial history record
        cursor.execute("SELECT id FROM inventory WHERE barcode=?", (barcode,))
        row = cursor.fetchone()
        if row:
            cursor.execute("INSERT INTO stock_history (item_id, record_date, quantity) VALUES (?, ?, ?)",
                           (row['id'], now, qty))

# ---------- Email alert ----------
def send_low_stock_email(item_name, barcode, qty_remaining):
    """
    Send a simple low-stock email to EMAIL_USER. Returns (success, message).
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_USER
        msg['Subject'] = f"[ALERT] Low Stock: {item_name} ({barcode})"
        body = f"Attention,\n\nItem '{item_name}' (Barcode: {barcode}) has low stock.\nRemaining quantity: {qty_remaining}\n\nPlease restock soon.\n\n-- Supermarket System"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# ---------- PDF receipt ----------
def generate_neat_pdf(filepath, shop_name, cashier, customer_name, items, subtotal, tax, total):
    if REPORTLAB_AVAILABLE:
        try:
            c = pdfcanvas.Canvas(filepath, pagesize=A4)
            width, height = A4
            margin = 20 * mm
            y = height - margin

            # header
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margin, y, shop_name)
            y -= 8 * mm
            c.setFont("Helvetica", 9)
            c.drawString(margin, y, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            c.drawRightString(width - margin, y, f"Cashier: {cashier}")
            y -= 8 * mm
            c.line(margin, y, width - margin, y)
            y -= 6 * mm

            # table header
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin, y, "Item")
            c.drawRightString(width - margin - 120, y, "Qty")
            c.drawRightString(width - margin - 60, y, "Price")
            c.drawRightString(width - margin, y, "Total")
            y -= 6 * mm
            c.setFont("Helvetica", 9)
            c.line(margin, y, width - margin, y)
            y -= 6 * mm

            # items
            for it in items:
                name = it['name'][:30]
                qty = it['quantity']
                price = it['price']
                line_total = price * qty
                c.drawString(margin, y, name)
                c.drawRightString(width - margin - 120, y, str(qty))
                c.drawRightString(width - margin - 60, y, f"₹{price:.2f}")
                c.drawRightString(width - margin, y, f"₹{line_total:.2f}")
                y -= 6 * mm
                if y < margin + 40:
                    c.showPage()
                    y = height - margin

            y -= 6 * mm
            c.line(margin, y, width - margin, y)
            y -= 6 * mm

            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin, y, f"Subtotal: ₹{subtotal:.2f}")
            y -= 6 * mm
            c.drawString(margin, y, f"Tax: ₹{tax:.2f}")
            y -= 6 * mm
            c.drawString(margin, y, f"TOTAL: ₹{total:.2f}")
            y -= 10 * mm

            c.setFont("Helvetica", 9)
            c.drawString(margin, y, "Thank you for shopping with us!")
            c.save()
            return True, "PDF generated"
        except Exception as e:
            return False, str(e)
    else:
        # fallback to .txt
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=== Supermarket Receipt ===\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Cashier: {cashier}    Customer: {customer_name}\n")
                f.write("="*40 + "\n")
                for it in items:
                    f.write(f"{it['name']} x{it['quantity']}  @ ₹{it['price']:.2f}  = ₹{it['price']*it['quantity']:.2f}\n")
                f.write("="*40 + "\n")
                f.write(f"Subtotal: ₹{subtotal:.2f}\n")
                f.write(f"Tax: ₹{tax:.2f}\n")
                f.write(f"TOTAL: ₹{total:.2f}\n")
                f.write("\nThank you!\n")
            return True, "Saved as text receipt (reportlab not installed)."
        except Exception as e:
            return False, str(e)

# ---------- Application ----------
class SupermarketApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Supermarket Management & Billing System")
        self.root.geometry("1180x720")
        self.current_user = None
        self.current_role = None
        self.current_bill = []  # list of dicts: barcode, name, price, quantity
        self.item_map = {} # Maps item name to ID for graph
        init_db()
        self.create_login_screen()

    # ---- Login Screen ----
    def create_login_screen(self):
        for w in self.root.winfo_children():
            w.destroy()
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(expand=True, fill='both')
        title = ttk.Label(frame, text="🛒 SUPERMARKET SYSTEM", font=("Arial", 24, "bold"))
        title.pack(pady=(10,20))
        login_box = ttk.Frame(frame, padding=12, relief="groove")
        login_box.pack(pady=6)
        ttk.Label(login_box, text="Username:").grid(row=0, column=0, padx=6, pady=6, sticky='e')
        self.username_entry = ttk.Entry(login_box, width=30)
        self.username_entry.grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(login_box, text="Password:").grid(row=1, column=0, padx=6, pady=6, sticky='e')
        self.password_entry = ttk.Entry(login_box, width=30, show="*")
        self.password_entry.grid(row=1, column=1, padx=6, pady=6)
        login_btn = ttk.Button(login_box, text="Login", command=self.handle_login)
        login_btn.grid(row=2, column=0, columnspan=2, pady=(8,6))
        hint = ttk.Label(login_box, text="Username: python | Password: python", foreground="gray")
        hint.grid(row=3, column=0, columnspan=2, pady=(4,2))
        self.root.bind('<Return>', lambda e: self.handle_login())

    def handle_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Enter username and password")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
        row = c.fetchone()
        conn.close()
        if row:
            self.current_user = username
            self.current_role = row["role"]
            self.show_main_ui()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")

    # ---- Main UI (tabs) ----
    def show_main_ui(self):
        for w in self.root.winfo_children():
            w.destroy()
        top = ttk.Frame(self.root)
        top.pack(fill='x')
        ttk.Label(top, text=f"Welcome, {self.current_user} ({self.current_role})", font=("Arial", 12, "bold")).pack(side='left', padx=10, pady=8)
        logout_btn = ttk.Button(top, text="Logout", command=self.logout)
        logout_btn.pack(side='right', padx=10, pady=8)

        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill='both', padx=8, pady=8)

        self.billing_frame = ttk.Frame(notebook)
        self.stock_frame = ttk.Frame(notebook)
        self.analytics_frame = ttk.Frame(notebook)

        notebook.add(self.billing_frame, text="Billing")
        notebook.add(self.stock_frame, text="Stock Dashboard")
        notebook.add(self.analytics_frame, text="Analytics")

        self.build_billing_page(self.billing_frame)
        self.build_stock_page(self.stock_frame)
        self.build_analytics_page(self.analytics_frame)

        # Load inventory
        self.load_inventory_cache()

    def logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.current_user = None
            self.current_role = None
            self.current_bill = []
            self.create_login_screen()

    # ---- Inventory cache ----
    def load_inventory_cache(self):
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM inventory ORDER BY name")
        self.inventory = [dict(r) for r in c.fetchall()]
        conn.close()
        
        # Build map for analytics
        self.item_map = {item['name']: item['id'] for item in self.inventory}

        # refresh UI components
        self.populate_product_list()
        self.populate_stock_table()
        self.populate_low_stock_warning()
        self.populate_combobox()

    # ---- Billing Page ----
    def build_billing_page(self, parent):
        # Left panel: products
        left = ttk.Frame(parent, relief="solid")
        left.pack(side='left', fill='both', expand=True, padx=(8,4), pady=8)
        # Right panel: bill
        right = ttk.Frame(parent, relief="solid", width=420)
        right.pack(side='right', fill='y', padx=(4,8), pady=8)

        # Search and barcode
        search_frame = ttk.Frame(left)
        search_frame.pack(fill='x', padx=8, pady=(8,4))
        ttk.Label(search_frame, text="Search:").pack(side='left', padx=4)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side='left', padx=4)
        search_entry.bind("<KeyRelease>", lambda e: self.populate_product_list())

        barcode_frame = ttk.Frame(left)
        barcode_frame.pack(fill='x', padx=8, pady=(4,8))
        ttk.Label(barcode_frame, text="Enter Barcode:").pack(side='left', padx=4)
        self.barcode_var = tk.StringVar()
        barcode_entry = ttk.Entry(barcode_frame, textvariable=self.barcode_var, width=30)
        barcode_entry.pack(side='left', padx=4)
        add_barcode_btn = ttk.Button(barcode_frame, text="ADD", command=self.add_by_barcode_button)
        add_barcode_btn.pack(side='left', padx=6)
        barcode_entry.bind('<Return>', lambda e: self.add_by_barcode_button())

        # Scrollable product list area (single-line entries)
        product_area = ttk.Frame(left)
        product_area.pack(fill='both', expand=True, padx=8, pady=6)
        canvas = tk.Canvas(product_area)
        self.prod_scrollbar = ttk.Scrollbar(product_area, orient="vertical", command=canvas.yview)
        self.product_list_inner = ttk.Frame(canvas)
        self.product_list_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.product_list_inner, anchor='nw')
        canvas.configure(yscrollcommand=self.prod_scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        self.prod_scrollbar.pack(side='right', fill='y')

        # Right side: current bill
        ttk.Label(right, text="🧾 Current Bill", font=("Arial", 14, "bold")).pack(pady=(8,6))
        cols = ("Name", "Price", "Qty", "Total")
        self.bill_tree = ttk.Treeview(right, columns=cols, show="headings", height=14)
        for c in cols:
            self.bill_tree.heading(c, text=c)
            self.bill_tree.column(c, width=95, anchor='center')
        self.bill_tree.pack(padx=8, pady=4)

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill='x', padx=8, pady=6)
        ttk.Button(btn_frame, text="Clear Bill", command=self.clear_bill).pack(side='left', padx=4)
        ttk.Button(btn_frame, text="Remove Item", command=self.remove_selected_bill_item).pack(side='left', padx=4)
        ttk.Button(btn_frame, text="Edit Qty", command=self.edit_selected_qty).pack(side='left', padx=4)

        # totals & customer
        self.subtotal_var = tk.StringVar(value="Subtotal: ₹0.00")
        self.tax_var = tk.StringVar(value=f"Tax ({int(DEFAULT_TAX_PERCENT*100)}%): ₹0.00")
        self.total_var = tk.StringVar(value="TOTAL: ₹0.00")
        ttk.Label(right, textvariable=self.subtotal_var).pack(anchor='w', padx=12, pady=(8,2))
        ttk.Label(right, textvariable=self.tax_var).pack(anchor='w', padx=12, pady=2)
        ttk.Label(right, textvariable=self.total_var, font=("Arial", 12, "bold")).pack(anchor='w', padx=12, pady=(2,10))

        ttk.Label(right, text="Customer Name:").pack(anchor='w', padx=12)
        self.customer_entry = ttk.Entry(right)
        self.customer_entry.pack(fill='x', padx=12, pady=(4,8))

        ttk.Button(right, text="Generate Bill (PDF)", command=self.process_checkout).pack(fill='x', padx=12, pady=(6,6))
        ttk.Button(right, text="Refresh Inventory", command=self.load_inventory_cache).pack(fill='x', padx=12, pady=(2,6))

    def populate_product_list(self):
        # clear existing
        for w in self.product_list_inner.winfo_children():
            w.destroy()
        q = self.search_var.get().strip().lower()
        items = [it for it in self.inventory if (q in it['name'].lower() or q in it['barcode'].lower() or q in it['category'].lower())] if q else self.inventory
        if not items:
            lbl = ttk.Label(self.product_list_inner, text="No items found.", foreground="gray")
            lbl.pack(padx=8, pady=8)
            return
        for it in items:
            line_text = f"{it['name']} (Barcode: {it['barcode']}) - ₹{it['price']:.2f} - Stock: {it['quantity']}"
            row = ttk.Frame(self.product_list_inner)
            row.pack(fill='x', padx=6, pady=4)
            lbl = ttk.Label(row, text=line_text)
            lbl.pack(side='left', padx=6)
            if it['quantity'] < LOW_STOCK_THRESHOLD:
                lbl.configure(foreground='red')
            add_btn = ttk.Button(row, text="+", width=3, command=lambda b=it['barcode']: self.add_item_by_barcode(b))
            add_btn.pack(side='right', padx=6)

    def add_item_by_barcode(self, barcode):
        # find item
        item = next((i for i in self.inventory if i['barcode'].strip().lower() == barcode.strip().lower()), None)
        if item is None:
            messagebox.showerror("Not found", f"No item with barcode: {barcode}")
            return
        if item['quantity'] <= 0:
            messagebox.showerror("Out of stock", f"{item['name']} is out of stock.")
            return
        # add or increment in current_bill
        for b in self.current_bill:
            if b['barcode'] == item['barcode']:
                b['quantity'] += 1
                break
        else:
            self.current_bill.append({'barcode': item['barcode'], 'name': item['name'], 'price': item['price'], 'quantity': 1})
        self.update_bill_display()

    def add_by_barcode_button(self):
        code = self.barcode_var.get().strip()
        if not code:
            messagebox.showinfo("Enter barcode", "Please enter a barcode or press + next to an item.")
            return
        self.add_item_by_barcode(code)
        self.barcode_var.set("")

    def update_bill_display(self):
        for r in self.bill_tree.get_children():
            self.bill_tree.delete(r)
        subtotal = 0.0
        for it in self.current_bill:
            line_total = it['price'] * it['quantity']
            subtotal += line_total
            self.bill_tree.insert("", "end", values=(it['name'], f"₹{it['price']:.2f}", it['quantity'], f"₹{line_total:.2f}"))
        tax = subtotal * DEFAULT_TAX_PERCENT
        total = subtotal + tax
        self.subtotal_var.set(f"Subtotal: ₹{subtotal:.2f}")
        self.tax_var.set(f"Tax ({int(DEFAULT_TAX_PERCENT*100)}%): ₹{tax:.2f}")
        self.total_var.set(f"TOTAL: ₹{total:.2f}")

    def clear_bill(self):
        if not self.current_bill:
            return
        if messagebox.askyesno("Confirm", "Clear current bill?"):
            self.current_bill = []
            self.update_bill_display()

    def remove_selected_bill_item(self):
        sel = self.bill_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select an item in the bill to remove.")
            return
        idx = self.bill_tree.index(sel[0])
        if 0 <= idx < len(self.current_bill):
            removed = self.current_bill.pop(idx)
            self.update_bill_display()
            messagebox.showinfo("Removed", f"Removed {removed['name']}")

    def edit_selected_qty(self):
        sel = self.bill_tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select an item in the bill to edit.")
            return
        idx = self.bill_tree.index(sel[0])
        item = self.current_bill[idx]
        win = tk.Toplevel(self.root)
        win.title("Edit Quantity")
        ttk.Label(win, text=f"Editing: {item['name']}").pack(padx=10, pady=8)
        qty_var = tk.StringVar(value=str(item['quantity']))
        qty_entry = ttk.Entry(win, textvariable=qty_var)
        qty_entry.pack(padx=10, pady=6)
        def save_qty():
            try:
                nq = int(qty_var.get())
                if nq <= 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("Invalid", "Enter a valid integer quantity (>=1).")
                return
            # check stock available in DB
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT quantity FROM inventory WHERE barcode=?", (item['barcode'],))
            row = c.fetchone()
            conn.close()
            avail = row['quantity'] if row else 0
            if nq > avail:
                messagebox.showerror("Not enough stock", f"Only {avail} available in inventory.")
                return
            item['quantity'] = nq
            self.update_bill_display()
            win.destroy()
        ttk.Button(win, text="Save", command=save_qty).pack(pady=8)

    # ---- Checkout ----
    def process_checkout(self):
        if not self.current_bill:
            messagebox.showinfo("Empty", "No items in the bill.")
            return
        # verify stock availability
        conn = get_conn()
        c = conn.cursor()
        for b in self.current_bill:
            c.execute("SELECT quantity FROM inventory WHERE barcode=?", (b['barcode'],))
            row = c.fetchone()
            if not row or row['quantity'] < b['quantity']:
                conn.close()
                messagebox.showerror("Stock error", f"Not enough stock for {b['name']}")
                return
        # deduct from inventory and record history
        for b in self.current_bill:
            c.execute("UPDATE inventory SET quantity = quantity - ? WHERE barcode=?", (b['quantity'], b['barcode']))
            # record stock_history: current remaining
            c.execute("SELECT id, quantity FROM inventory WHERE barcode=?", (b['barcode'],))
            rr = c.fetchone()
            if rr:
                item_id = rr['id']
                remaining = rr['quantity']
                c.execute("INSERT INTO stock_history (item_id, record_date, quantity) VALUES (?, ?, ?)",
                          (item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), remaining))
        # save the sale
        subtotal = sum(it['price'] * it['quantity'] for it in self.current_bill)
        tax = subtotal * DEFAULT_TAX_PERCENT
        total = subtotal + tax
        customer = self.customer_entry.get().strip() or "Walk-in"
        c.execute("INSERT INTO sales (sale_date, items_json, total_amount, customer_name) VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(self.current_bill), total, customer))
        conn.commit()
        conn.close()

        # refresh cache to reflect updated stock
        self.load_inventory_cache()

        # detect low-stock items and send emails
        low_items = []
        for b in self.current_bill:
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT name, barcode, quantity FROM inventory WHERE barcode=?", (b['barcode'],))
            row = c.fetchone()
            conn.close()
            if row and row['quantity'] < LOW_STOCK_THRESHOLD:
                low_items.append((row['name'], row['barcode'], row['quantity']))

        # save receipt (PDF or TXT)
        filename = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                filetypes=[("PDF Files", "*.pdf"), ("Text Files", "*.txt"), ("All Files", "*.*")],
                                                initialfile=f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        if filename:
            ok, msg = generate_neat_pdf(filename, "Supermarket System", self.current_user, customer, self.current_bill, subtotal, tax, total)
            if ok:
                messagebox.showinfo("Receipt", f"Receipt saved: {filename}")
            else:
                messagebox.showwarning("Receipt", f"Could not save PDF: {msg}")

        # show low-stock warnings and send emails
        if low_items:
            lines = [f"{n} (Barcode: {b}) - Remaining: {q}" for n,b,q in low_items]
            # try sending email for each low item
            for n,b,q in low_items:
                success, resp = send_low_stock_email(n, b, q)
                if not success:
                    # print to console for debugging but don't block the app
                    print("Email send failed:", resp)
            messagebox.showwarning("Low Stock Alert", "Low-stock items detected:\n\n" + "\n".join(lines))

        # clear current bill
        self.current_bill = []
        self.update_bill_display()
        try:
            self.customer_entry.delete(0, 'end')
        except Exception:
            pass

    # ---- Stock Dashboard ----
    def build_stock_page(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill='x', padx=8, pady=8)
        ttk.Label(top, text="Stock Dashboard", font=("Arial", 14, "bold")).pack(side='left', padx=6)
        
        # Refresh button only
        ttk.Button(top, text="Refresh", command=self.load_inventory_cache).pack(side='right', padx=6)

        # Low-stock warning label area
        warn_frame = ttk.Frame(parent, padding=6, relief='flat')
        warn_frame.pack(fill='x', padx=8, pady=(0,6))
        self.low_stock_label = ttk.Label(warn_frame, text="", foreground="red", justify='left', font=("Arial", 10, "bold"))
        self.low_stock_label.pack(anchor='w')

        # Inventory table
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill='both', expand=True, padx=8, pady=6)
        cols = ("ID", "Name", "Category", "Price", "Stock", "Barcode")
        self.stock_tree = ttk.Treeview(table_frame, columns=cols, show='headings')
        for c in cols:
            self.stock_tree.heading(c, text=c)
            if c == "Name":
                self.stock_tree.column(c, width=260)
            else:
                self.stock_tree.column(c, width=100, anchor='center')
        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self.stock_tree.yview)
        self.stock_tree.configure(yscrollcommand=vsb.set)
        self.stock_tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

    def populate_stock_table(self):
        # clear
        for r in self.stock_tree.get_children():
            self.stock_tree.delete(r)
        # fill
        for it in self.inventory:
            vals = (it['id'], it['name'], it['category'], f"₹{it['price']:.2f}", it['quantity'], it['barcode'])
            iid = self.stock_tree.insert("", "end", values=vals)
            if it['quantity'] < LOW_STOCK_THRESHOLD:
                # tag the item as low stock
                self.stock_tree.tag_configure('low', foreground='red')
                current_tags = self.stock_tree.item(iid, 'tags') or ()
                self.stock_tree.item(iid, tags=current_tags + ('low',))

    def populate_low_stock_warning(self):
        low = [it for it in self.inventory if it['quantity'] < LOW_STOCK_THRESHOLD]
        if not low:
            self.low_stock_label.config(text="No low-stock items.")
        else:
            lines = ["⚠ LOW STOCK ITEMS:"]
            for it in low:
                lines.append(f"{it['name']} (Barcode: {it['barcode']}) - Stock: {it['quantity']}")
            self.low_stock_label.config(text="\n".join(lines))

    # ---- Analytics Page (Graph) ----
    def build_analytics_page(self, parent):
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(top_frame, text="Select Product for Analysis:").pack(side='left', padx=5)
        
        self.analytics_combo = ttk.Combobox(top_frame, state="readonly", width=40)
        self.analytics_combo.pack(side='left', padx=5)
        
        ttk.Button(top_frame, text="Load Graph", command=self.plot_item_history).pack(side='left', padx=5)

        self.graph_container = ttk.Frame(parent, relief="sunken", borderwidth=1)
        self.graph_container.pack(fill='both', expand=True, padx=10, pady=10)

        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(self.graph_container, text="Matplotlib not installed. Graphs unavailable.", foreground="red").pack(pady=50)

    def populate_combobox(self):
        # Populate with item names
        names = sorted(list(self.item_map.keys()))
        self.analytics_combo['values'] = names
        if names:
            self.analytics_combo.current(0)

    def plot_item_history(self):
        if not MATPLOTLIB_AVAILABLE:
            return

        item_name = self.analytics_combo.get()
        if not item_name or item_name not in self.item_map:
            return
        
        item_id = self.item_map[item_name]
        
        # Fetch history
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT record_date, quantity FROM stock_history WHERE item_id=? ORDER BY record_date", (item_id,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            messagebox.showinfo("No Data", f"No history found for {item_name}")
            return

        dates = [datetime.strptime(r['record_date'], "%Y-%m-%d %H:%M:%S") for r in rows]
        quants = [r['quantity'] for r in rows]

        # Clear previous graph
        for widget in self.graph_container.winfo_children():
            widget.destroy()

        # Plot
        fig = Figure(figsize=(8, 5), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(dates, quants, marker='o', linestyle='-', color='blue')
        ax.set_title(f"Stock History: {item_name}")
        ax.set_xlabel("Time")
        ax.set_ylabel("Quantity")
        ax.grid(True)
        
        # Format date on X axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        fig.autofmt_xdate()

        canvas = FigureCanvasTkAgg(fig, master=self.graph_container)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

# ---------- Run ----------
def main():
    root = tk.Tk()
    app = SupermarketApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
