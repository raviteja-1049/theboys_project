from flask import Flask, render_template, request, redirect, session, url_for, jsonify, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DATABASE = 'grocery.db'

# Image upload configuration
UPLOAD_FOLDER = 'static/uploads/products'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB limit

# Create upload folder if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    with sqlite3.connect(DATABASE) as con:
        cur = con.cursor()
        
        # Users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            is_admin BOOLEAN DEFAULT 0
        )""")
        
        # Admins table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )""")
        
        # Products table
        cur.execute('''CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        price REAL,
                        image TEXT,
                        description TEXT,
                        category TEXT,
                        stock INTEGER DEFAULT 100
                    )''')
        
        # Orders table
        cur.execute('''CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        product_id INTEGER,
                        product_name TEXT,
                        price REAL,
                        quantity INTEGER,
                        address TEXT,
                        phone TEXT,
                        payment_method TEXT,
                        delivery_charge REAL DEFAULT 30,
                        delivery_time TEXT,
                        status TEXT DEFAULT 'Processing',
                        order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        
        # Cart table
        cur.execute('''CREATE TABLE IF NOT EXISTS cart (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        product_id INTEGER,
                        quantity INTEGER DEFAULT 1,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        
        # Insert default admin
        try:
            hashed_password = hash_password("admin123")
            cur.execute("INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)", 
                       ("admin", hashed_password))
            
            # Insert sample products
            sample_products = [
                ("Apple", 50, "uploads/products/apple.jpg", "Fresh red apples", "Fruits", 100),
                ("Banana", 30, "uploads/products/banana.jpg", "Ripe bananas", "Fruits", 100),
                ("Milk", 25, "uploads/products/milk.jpg", "1L Fresh milk", "Dairy", 100)
            ]
            cur.executemany("INSERT INTO products (name, price, image, description, category, stock) VALUES (?, ?, ?, ?, ?, ?)",
                          sample_products)
            con.commit()
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
            con.rollback()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd = request.form.get('password', '').strip()
        
        if not uname or not pwd:
            flash("Username and password are required", 'error')
            return redirect('/login')
        
        hashed_pwd = hash_password(pwd)
        
        with sqlite3.connect(DATABASE) as con:
            # Check in users table
            user = con.execute("SELECT * FROM users WHERE username=? AND password=?", 
                             (uname, hashed_pwd)).fetchone()
            if user:
                session['user'] = uname
                session['is_admin'] = False
                return redirect('/products')
            
            # Check in admins table
            admin = con.execute("SELECT * FROM admins WHERE username=? AND password=?", 
                              (uname, hashed_pwd)).fetchone()
            if admin:
                session['admin'] = uname
                session['is_admin'] = True
                return redirect('/admin_dashboard')
            
            flash("Invalid credentials", 'error')
            return redirect('/login')
    return render_template('login.html')

@app.route('/products')
def products():
    if 'user' not in session:
        return redirect('/login')

    with sqlite3.connect(DATABASE) as con:
        products = con.execute("SELECT * FROM products WHERE stock > 0").fetchall()
        cart_count = con.execute("SELECT COUNT(*) FROM cart WHERE username=?", 
                               (session['user'],)).fetchone()[0]

    return render_template('products.html', products=products, cart_count=cart_count)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if 'user' not in session:
        return redirect('/login')
    
    with sqlite3.connect(DATABASE) as con:
        product = con.execute("SELECT * FROM products WHERE id=?", 
                            (product_id,)).fetchone()
        if not product:
            flash("Product not found", 'error')
            return redirect('/products')
    return render_template('product_detail.html', product=product)

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user' not in session:
        return redirect('/login')
    
    with sqlite3.connect(DATABASE) as con:
        stock = con.execute("SELECT stock FROM products WHERE id=?", 
                           (product_id,)).fetchone()
        if not stock or stock[0] <= 0:
            flash("Product out of stock", 'error')
            return redirect('/products')
        
        existing = con.execute("SELECT * FROM cart WHERE username=? AND product_id=?", 
                             (session['user'], product_id)).fetchone()
        if existing:
            con.execute("UPDATE cart SET quantity = quantity + 1 WHERE id=?", 
                       (existing[0],))
        else:
            con.execute("INSERT INTO cart (username, product_id) VALUES (?, ?)", 
                       (session['user'], product_id))
        con.commit()
    
    flash("Product added to cart", 'success')
    return redirect('/products')

@app.route('/update_cart/<int:product_id>/<action>', methods=['POST'])
def update_cart(product_id, action):
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Not logged in'})
    
    with sqlite3.connect(DATABASE) as con:
        item = con.execute("SELECT quantity FROM cart WHERE username=? AND product_id=?", 
                          (session['user'], product_id)).fetchone()
        
        if not item:
            return jsonify({'success': False, 'error': 'Item not in cart'})
        
        new_quantity = item[0]
        if action == 'increase':
            stock = con.execute("SELECT stock FROM products WHERE id=?", 
                              (product_id,)).fetchone()[0]
            if new_quantity >= stock:
                return jsonify({'success': False, 'error': 'Not enough stock'})
            new_quantity += 1
        elif action == 'decrease' and item[0] > 1:
            new_quantity -= 1
        
        con.execute("UPDATE cart SET quantity=? WHERE username=? AND product_id=?", 
                   (new_quantity, session['user'], product_id))
        
        cart_items = con.execute('''SELECT p.id, p.name, p.price, c.quantity 
                                  FROM products p JOIN cart c ON p.id = c.product_id 
                                  WHERE c.username=?''', (session['user'],)).fetchall()
        cart_total = sum(item[2] * item[3] for item in cart_items)
        cart_count = sum(item[3] for item in cart_items)
        
        con.commit()
    
    return jsonify({
        'success': True,
        'newQuantity': new_quantity,
        'cartTotal': cart_total,
        'cartCount': cart_count,
        'grandTotal': cart_total + 30
    })

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'user' not in session:
        return redirect('/login')
    
    with sqlite3.connect(DATABASE) as con:
        con.execute("DELETE FROM cart WHERE username=? AND product_id=?", 
                   (session['user'], product_id))
        con.commit()
    
    flash("Item removed from cart", 'success')
    return redirect('/view_cart')

@app.route('/view_cart')
def view_cart():
    if 'user' not in session:
        return redirect('/login')
    
    with sqlite3.connect(DATABASE) as con:
        cart_items = con.execute('''SELECT p.id, p.name, p.price, p.image, c.quantity, p.stock 
                                  FROM products p JOIN cart c ON p.id = c.product_id 
                                  WHERE c.username=?''', (session['user'],)).fetchall()
        total = sum(item[2] * item[4] for item in cart_items)
        cart_count = sum(item[4] for item in cart_items)
    
    return render_template('cart.html', 
                         cart_items=cart_items, 
                         total=total, 
                         delivery_charge=30,
                         cart_count=cart_count)

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user' not in session:
        return redirect('/login')

    if request.method == 'GET':
        with sqlite3.connect(DATABASE) as con:
            user = con.execute("SELECT address, phone FROM users WHERE username=?", 
                             (session['user'],)).fetchone()
            cart_items = con.execute('''SELECT p.id, p.name, p.price, c.quantity, p.stock
                                      FROM products p JOIN cart c ON p.id = c.product_id
                                      WHERE c.username=?''', (session['user'],)).fetchall()
            
            if not cart_items:
                flash("Your cart is empty", 'error')
                return redirect('/products')
            
            total = sum(item[2] * item[3] for item in cart_items)
            delivery_charge = 30
            grand_total = total + delivery_charge
            
            out_of_stock = any(item[3] > item[4] for item in cart_items)
            if out_of_stock:
                flash("Some items in your cart are out of stock", 'error')
                return redirect('/view_cart')
            
        return render_template('checkout.html',
                            user=user,
                            cart_items=cart_items,
                            total=total,
                            delivery_charge=delivery_charge,
                            grand_total=grand_total)
    
    elif request.method == 'POST':
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        payment_method = request.form.get('payment_method', 'COD').strip()
        
        if not address or not phone:
            flash("Address and phone number are required", 'error')
            return redirect('/checkout')
        
        with sqlite3.connect(DATABASE) as con:
            try:
                cart_items = con.execute('''SELECT p.id, p.name, p.price, c.quantity, p.stock
                                          FROM products p JOIN cart c ON p.id = c.product_id
                                          WHERE c.username=?''', (session['user'],)).fetchall()
                
                if not cart_items:
                    flash("Your cart is empty", 'error')
                    return redirect('/products')
                
                delivery_time = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
                
                for item in cart_items:
                    product_id, name, price, quantity, stock = item
                    
                    if quantity > stock:
                        flash(f"Not enough stock for {name}", 'error')
                        return redirect('/view_cart')
                    
                    con.execute('''INSERT INTO orders 
                                 (username, product_id, product_name, price, quantity,
                                  address, phone, payment_method, delivery_time)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (session['user'], product_id, name, price, quantity,
                               address, phone, payment_method, delivery_time))
                    
                    con.execute("UPDATE products SET stock = stock - ? WHERE id = ?",
                              (quantity, product_id))
                
                con.execute("DELETE FROM cart WHERE username = ?", (session['user'],))
                con.commit()
                
                flash("Order placed successfully!", 'success')
                return redirect('/orders')
            
            except Exception as e:
                con.rollback()
                flash(f"Error processing order: {str(e)}", 'error')
                return redirect('/checkout')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if not username or not password:
            flash("Username and password are required", 'error')
            return redirect('/register')
        
        hashed_password = hash_password(password)
        
        with sqlite3.connect(DATABASE) as con:
            try:
                con.execute("INSERT INTO users (username, password, address, phone) VALUES (?, ?, ?, ?)",
                    (username, hashed_password, address, phone))
                con.commit()
                session['user'] = username
                flash('Registration successful!', 'success')
                return redirect('/products')
            except sqlite3.IntegrityError:
                flash('Username already exists', 'error')
                return redirect('/register')
    
    return render_template('register.html')

@app.route('/orders')
def user_orders():
    if 'user' not in session:
        return redirect('/login')
    
    with sqlite3.connect(DATABASE) as con:
        orders = con.execute('''SELECT o.id, o.product_name, o.price, o.quantity, 
                               o.delivery_charge, o.status, o.order_date
                               FROM orders o
                               WHERE o.username=?
                               ORDER BY o.order_date DESC''', 
                            (session['user'],)).fetchall()
    return render_template('user_orders.html', orders=orders)

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin' not in session:
        flash('Please login as admin to access this page', 'error')
        return redirect(url_for('admin_login'))
    
    try:
        with sqlite3.connect(DATABASE) as con:
            # Get products with proper type conversion
            products = []
            raw_products = con.execute("""
                SELECT id, name, price, stock 
                FROM products 
                ORDER BY id DESC 
                LIMIT 50
            """).fetchall()
            
            for product in raw_products:
                products.append((
                    product[0],
                    product[1],
                    float(product[2]) if product[2] is not None else 0.0,
                    product[3]
                ))
            
            # Get recent orders with proper type conversion
            orders = []
            raw_orders = con.execute("""
                SELECT o.id, o.username, o.product_name, o.price, o.quantity,
                       o.address, o.phone, o.payment_method, o.delivery_charge,
                       o.delivery_time, o.order_date, o.status
                FROM orders o
                ORDER BY o.order_date DESC 
                LIMIT 50
            """).fetchall()
            
            for order in raw_orders:
                orders.append((
                    order[0],  # id
                    order[1],  # username
                    order[2],  # product_name
                    float(order[3]) if order[3] is not None else 0.0,  # price
                    order[4],  # quantity
                    order[5],  # address
                    order[6],  # phone
                    order[7],  # payment_method
                    float(order[8]) if order[8] is not None else 0.0,  # delivery_charge
                    order[9],  # delivery_time
                    order[10],  # order_date
                    order[11]   # status
                ))
            
            # Get statistics
            stats = con.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM products) as total_products,
                    (SELECT COUNT(*) FROM orders) as total_orders,
                    (SELECT COUNT(*) FROM users WHERE is_admin = 0) as total_users,
                    (SELECT COUNT(*) FROM users WHERE is_admin = 1) as total_admins
            """).fetchone()
            
            stats = {
                'total_products': int(stats[0]) if stats[0] is not None else 0,
                'total_orders': int(stats[1]) if stats[1] is not None else 0,
                'total_users': int(stats[2]) if stats[2] is not None else 0,
                'total_admins': int(stats[3]) if stats[3] is not None else 0
            }
            
        return render_template('admin_dashboard.html', 
                            products=products, 
                            orders=orders,
                            stats=stats)
                            
    except sqlite3.Error as e:
        flash(f'Database error: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect('/admin_login')
        
        hashed_password = hash_password(password)
        
        with sqlite3.connect(DATABASE) as con:
            admin = con.execute("SELECT * FROM admins WHERE username=? AND password=?",
                (username, hashed_password)).fetchone()
            
            if admin:
                session['admin'] = username
                session['is_admin'] = True
                return redirect('/admin_dashboard')
            else:
                flash('Invalid admin credentials', 'error')
                return redirect('/admin_login')
    
    return render_template('admin_login.html')

@app.route('/add_product', methods=['POST'])
def add_product():
    if 'admin' not in session:
        return redirect('/admin_login')

    name = request.form.get('name', '').strip()
    price = request.form.get('price', '0')
    description = request.form.get('description', '').strip()
    category = request.form.get('category', 'Other').strip()
    stock = request.form.get('stock', '100')
    
    if not name or not price:
        flash("Product name and price are required", 'error')
        return redirect('/admin_dashboard')
    
    try:
        price = float(price)
        stock = int(stock)
    except ValueError:
        flash("Invalid price or stock value", 'error')
        return redirect('/admin_dashboard')
    
    if 'image' not in request.files:
        flash("No image file selected", 'error')
        return redirect('/admin_dashboard')
        
    file = request.files['image']
    
    if file.filename == '':
        flash("No image selected", 'error')
        return redirect('/admin_dashboard')
        
    if not allowed_file(file.filename):
        flash("Invalid file type. Only PNG, JPG, JPEG, GIF allowed.", 'error')
        return redirect('/admin_dashboard')

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        image_path = f"uploads/products/{filename}"
        
        with sqlite3.connect(DATABASE) as con:
            con.execute('''INSERT INTO products 
                          (name, price, image, description, category, stock)
                          VALUES (?, ?, ?, ?, ?, ?)''', 
                       (name, price, image_path, description, category, stock))
            con.commit()
            
        flash("Product added successfully", 'success')
        return redirect('/admin_dashboard')
        
    except Exception as e:
        flash(f"Error adding product: {str(e)}", 'error')
        return redirect('/admin_dashboard')

@app.route('/update_product/<int:product_id>', methods=['POST'])
def update_product(product_id):
    if 'admin' not in session:
        return redirect('/admin_login')
    
    name = request.form.get('name', '').strip()
    price = request.form.get('price', '0')
    description = request.form.get('description', '').strip()
    category = request.form.get('category', 'Other').strip()
    stock = request.form.get('stock', '100')
    
    if not name or not price:
        flash("Product name and price are required", 'error')
        return redirect('/admin_dashboard')
    
    try:
        price = float(price)
        stock = int(stock)
    except ValueError:
        flash("Invalid price or stock value", 'error')
        return redirect('/admin_dashboard')
    
    with sqlite3.connect(DATABASE) as con:
        if 'image' in request.files and request.files['image'].filename != '':
            file = request.files['image']
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_path = f"uploads/products/{filename}"
                
                old_image = con.execute("SELECT image FROM products WHERE id=?", 
                                      (product_id,)).fetchone()
                if old_image and old_image[0]:
                    try:
                        os.remove(os.path.join('static', old_image[0]))
                    except:
                        pass
                
                con.execute('''UPDATE products SET 
                              name=?, price=?, image=?, description=?, category=?, stock=?
                              WHERE id=?''',
                           (name, price, image_path, description, category, stock, product_id))
            else:
                flash("Invalid image file type", 'error')
                return redirect('/admin_dashboard')
        else:
            con.execute('''UPDATE products SET 
                          name=?, price=?, description=?, category=?, stock=?
                          WHERE id=?''',
                       (name, price, description, category, stock, product_id))
        
        con.commit()
    
    flash("Product updated successfully", 'success')
    return redirect('/admin_dashboard')

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if 'admin' not in session:
        return redirect('/admin_login')
    
    with sqlite3.connect(DATABASE) as con:
        image_path = con.execute("SELECT image FROM products WHERE id=?", 
                               (product_id,)).fetchone()
        if image_path and image_path[0]:
            try:
                os.remove(os.path.join('static', image_path[0]))
            except:
                pass
        
        con.execute("DELETE FROM products WHERE id=?", (product_id,))
        con.commit()
    
    flash("Product deleted successfully", 'success')
    return redirect('/admin_dashboard')

@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'admin' not in session:
        return redirect('/admin_login')
    
    new_status = request.form.get('status', '').strip()
    
    if not new_status:
        flash("Status is required", 'error')
        return redirect('/admin_dashboard')
    
    with sqlite3.connect(DATABASE) as con:
        con.execute("UPDATE orders SET status=? WHERE id=?", 
                   (new_status, order_id))
        con.commit()
    
    flash("Order status updated", 'success')
    return redirect('/admin_dashboard')

@app.route('/get_cart_count')
def get_cart_count():
    if 'user' in session:
        with sqlite3.connect(DATABASE) as con:
            count = con.execute("SELECT COUNT(*) FROM cart WHERE username=?", 
                              (session['user'],)).fetchone()[0]
        return jsonify({'count': count})
    return jsonify({'count': 0})

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect('/products')
    
    with sqlite3.connect(DATABASE) as con:
        results = con.execute('''SELECT * FROM products 
                               WHERE name LIKE ? OR description LIKE ? OR category LIKE ?
                               LIMIT 20''',
                            (f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
    
    return render_template('search_results.html', results=results, query=query)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)
