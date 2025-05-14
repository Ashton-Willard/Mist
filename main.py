from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "Admin":
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("store"))  # Redirect non-admin users
        return f(*args, **kwargs)
    return decorated_function


app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:Cset-155@localhost/mistdb"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Models
class RefundRequest(db.Model):
    __tablename__ = "refundrequest"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("purchased_game.id"), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Pending")  # Status: Pending, Approved, Denied
    user = db.relationship("User", backref="refunds")  # ✅ Ensure this exists!
    game = db.relationship("PurchasedGame", backref="refund_requests")  # ✅ Ensure this exists!


class GameReview(db.Model):
    __tablename__ = "gamereview"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("purchased_game.id"), nullable=False)
    review_text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # Optional: Allow star ratings (1-5)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="reviews")
    game = db.relationship("PurchasedGame", backref="reviews")

wishlist_table = db.Table('wishlist',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('game_id', db.Integer, db.ForeignKey('game.id'))
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    wishlist = db.relationship('Game', secondary=wishlist_table, backref='wishlisted_by')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    genres = db.Column(db.String(100))
    image_filename = db.Column(db.String(100))  # Add this line
    image_url = db.Column(db.String(255))
    # Add this:
    vendor_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # assuming User table is named 'user'

    vendor = db.relationship('User', backref='games')


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    status = db.Column(db.String(20), default="Pending")

class Library(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    added_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())

class PurchasedGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # User that purchased the game
    title = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes

@app.route('/library/review/<int:game_id>', methods=['POST'])
@login_required
def submit_review(game_id):
    review_text = request.form.get("review_text")
    rating = request.form.get("rating", type=int)

    print(f"DEBUG: Review Submission -> User ID: {current_user.id}, Game ID: {game_id}, Rating: {rating}")  # ✅ Debugging

    if not review_text or rating is None:
        flash("Review text and rating are required.", "error")
        return redirect(url_for("library"))

    purchased_game = PurchasedGame.query.filter_by(user_id=current_user.id, id=game_id).first()
    if not purchased_game:
        flash("You can only review games you've purchased.", "error")
        return redirect(url_for("library"))

    new_review = GameReview(user_id=current_user.id, game_id=game_id, review_text=review_text, rating=rating)  # ✅ Uses game_id from URL
    db.session.add(new_review)
    db.session.commit()

    flash("Review submitted!", "success")
    return redirect(url_for("library"))

@app.route('/library/refund/<int:game_id>', methods=['POST'])
@login_required
def submit_refund(game_id):
    reason = request.form.get("reason")

    print(f"DEBUG: Received Refund Request -> User ID: {current_user.id}, Game ID: {game_id}, Reason: {reason}")  # ✅ Debugging

    new_refund = RefundRequest(user_id=current_user.id, game_id=game_id, reason=reason, status="Pending")
    db.session.add(new_refund)
    db.session.commit()

    print(f"DEBUG: Refund Saved -> ID: {new_refund.id}, User ID: {new_refund.user_id}, Reason: {new_refund.reason}, Status: {new_refund.status}")  # ✅ Logs saved values

    flash("Refund request submitted!", "success")
    return redirect(url_for("library"))

@app.route('/admin/approve_refund/<int:refund_id>', methods=['POST'])
@admin_required
def approve_refund(refund_id):
    refund = RefundRequest.query.get(refund_id)
    if refund:
        refund.status = "Approved"
        db.session.commit()
        flash("Refund approved!", "success")
    return redirect(url_for('admin_reviews'))

@app.route('/admin/deny_refund/<int:refund_id>', methods=['POST'])
@admin_required
def deny_refund(refund_id):
    refund = RefundRequest.query.get(refund_id)
    if refund:
        refund.status = "Denied"
        db.session.commit()
        flash("Refund denied!", "error")
    return redirect(url_for('admin_reviews'))

@app.route('/admin/refunds')
@admin_required  # Ensure only admins can access
def view_refunds():
    refund_requests = RefundRequest.query.all()
    return render_template("admin_refunds.html", refund_requests=refund_requests)

@app.route('/admin/reviews')
@admin_required
def admin_reviews():
    reviews = GameReview.query.all()
    refund_requests = RefundRequest.query.filter_by(status="Pending").all()  # ✅ Only show pending refunds
    return render_template("admin_reviews.html", reviews=reviews, refund_requests=refund_requests)

@app.route('/admin/delete_review/<int:review_id>', methods=['POST'])
@admin_required
def delete_review(review_id):
    review = GameReview.query.get(review_id)
    if review:
        db.session.delete(review)
        db.session.commit()
        flash("Review deleted successfully!", "info")  # ✅ Flash message
    return redirect(url_for('admin_reviews'))

@app.route("/")
def index():
    featured_games = Game.query.limit(5).all()
    popular_games = Game.query.order_by(Game.price.desc()).limit(6).all()
    return render_template("index.html", featured_games=featured_games, popular_games=popular_games)

@app.route('/store')
@login_required
def store():
    all_games = Game.query.all()
    cart = session.get('cart', [])
    cart_game_ids = [item['id'] for item in cart]
    return render_template('store.html', all_games=all_games, cart_game_ids=cart_game_ids)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "Customer")

        # ✅ Prevent NULL values from being inserted
        if not username or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("signup"))

        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)  # ✅ Ensures password is hashed

        db.session.add(new_user)
        db.session.commit()  # 🚀 Guarantees data gets saved!

        print(f"DEBUG: User created -> {new_user.username}, {new_user.email}, {new_user.role}")  # ✅ Logs actual values

        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next') or url_for('store')
            flash("Login successful!", "success")
            return redirect(next_page)

        flash("Incorrect email or password. Please try again.", "error")
    return render_template("login.html")



@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role not in ['Admin', 'Vendor']:
        flash("Access denied.", "danger")
        return redirect(url_for('store'))

    games = Game.query.all()
    return render_template('dashboard.html', games=games)

@app.route('/add_game', methods=['GET', 'POST'])
@login_required
def add_game():
    if current_user.role not in ['Admin', 'Vendor']:
        flash("You don't have permission to add games.")
        return redirect(url_for('store'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        image_url = request.form['image_url']
        genres = request.form['genres']
        vendor_id = current_user.id  # ✅ THIS LINE IS ESSENTIAL

        new_game = Game(
            title=title,
            description=description,
            price=price,
            image_url=image_url,
            image_filename=request.form['image_filename'],
            genres=genres,
            vendor_id=vendor_id  # ✅ Must NOT be None
        )
        db.session.add(new_game)
        db.session.commit()
        flash("Game added successfully!")
        return redirect(url_for('store'))

    return render_template('add_game.html')


@app.route('/search_genre', methods=['GET'])
def search_genre():
    genre_query = request.args.get('genre')
    if genre_query:
        matching_games = Game.query.filter(Game.genres.ilike(f'%{genre_query}%')).all()
    else:
        matching_games = []
    return render_template('genre_search.html', games=matching_games, search_term=genre_query)

@app.route('/genre_filter')
def genre_filter():
    genre = request.args.get('genre')
    if genre:
        games = Game.query.filter(Game.genres.ilike(f'%{genre}%')).all()
    else:
        games = Game.query.all()

    # Extract unique genres from all games
    all_games = Game.query.all()
    genre_set = set()
    for game in all_games:
        if game.genres:
            for g in game.genres.split(','):
                genre_set.add(g.strip())

    return render_template('genre_filter.html', games=games, genres=sorted(genre_set), selected_genre=genre)

@app.route('/helpy')
def helpy():
    games = Game.query.all()  # Fetch all games from the database
    return render_template('helpy.html', games=games)

@app.route("/purchase/<int:game_id>", methods=["POST"])
@login_required
def purchase_game(game_id):
    game = Game.query.get_or_404(game_id)
    existing_entry = Library.query.filter_by(user_id=current_user.id, game_id=game.id).first()
    if existing_entry:
        flash("You already own this game!", "info")
        return redirect(url_for("store"))

    new_entry = Library(user_id=current_user.id, game_id=game.id)
    db.session.add(new_entry)

    order = Order.query.filter_by(user_id=current_user.id, game_id=game.id).first()
    if order:
        order.status = "Completed"
        db.session.delete(order)

    db.session.commit()
    flash("Game added to your library!", "success")
    return redirect(url_for("library"))

@app.route('/delete-game/<int:game_id>', methods=['POST'])
@login_required
def delete_game(game_id):
    if current_user.role not in ['Admin', 'Vendor']:
        flash("Access denied.", "danger")
        return redirect(url_for('store'))

    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    flash("Game deleted successfully.", "success")
    return redirect(url_for('dashboard'))


@app.route('/library')
@login_required
def library():
    user_id = current_user.id
    owned_games = db.session.query(Game).join(Library).filter(Library.user_id == user_id).all()

    print("Owned Games:", owned_games)

    return render_template('library.html', games=owned_games)

@app.before_request
def make_cart_available():
    if 'cart' not in session:
        session['cart'] = []

@app.route('/add_to_cart/<int:game_id>', methods=['POST'])
def add_to_cart(game_id):
    game = Game.query.get_or_404(game_id)

    # Initialize cart if it doesn't exist
    if 'cart' not in session:
        session['cart'] = []

    # Avoid duplicates
    if not any(item['id'] == game.id for item in session['cart']):
        session['cart'].append({
            'id': game.id,
            'title': game.title,
            'price': float(game.price),
            'image_url': game.image_url,
            'image_filename': game.image_filename
        })

    session.modified = True
    return redirect(url_for('store'))

@app.route('/game/<int:game_id>')
def game_detail(game_id):
    game = Game.query.get_or_404(game_id)

    # Fetch cart from session (adjust to your logic)
    cart = session.get('cart', [])
    cart_game_ids = [item['id'] for item in cart]

    return render_template('game_detail.html', game=game, cart_game_ids=cart_game_ids)

@app.context_processor
def cart_count():
    cart = session.get('cart', [])
    return {'cart_item_count': len(cart)}

@app.route("/add-placeholder-to-cart", methods=["POST"])
def add_placeholder_to_cart():
    if 'cart' not in session:
        session['cart'] = []
    cart = session['cart']
    cart.append({
        "id": "placeholder",
        "title": "Elden Ring Neightreign",
        "price": 69.99
    })
    session['cart'] = cart
    flash("Placeholder game added to cart!", "success")
    return redirect(url_for("cart"))

@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    total_price = sum(item['price'] for item in cart_items)
    return render_template('cart.html', cart=cart_items, total_price=total_price)


@app.route("/remove-from-cart/<game_id>", methods=["POST"])
def remove_from_cart(game_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if str(item['id']) != game_id]
    session['cart'] = cart
    flash("Game removed from cart!", "success")
    return redirect(url_for('cart'))

@app.route("/points")
@login_required
def points():
    return render_template("points.html")

@app.route('/filter', methods=['GET', 'POST'])
def filter():
    return render_template('filter.html')

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    user_id = current_user.id
    cart = session.get('cart', [])

    if not cart:
        flash("Your cart is empty!", "error")
        return redirect(url_for('cart'))

    # Calculate the total price
    total_price = sum(item['price'] for item in cart)  # Ensure price is part of the cart items

    if request.method == 'POST':
        for item in cart:
            game_id = item['id']

            existing_entry = Library.query.filter_by(user_id=user_id, game_id=game_id).first()
            if not existing_entry:
                new_entry = Library(user_id=user_id, game_id=game_id)
                db.session.add(new_entry)

        db.session.commit()

        session['cart'] = []  # Clear the cart after purchase
        flash("Purchase successful! Your games are now in your library.", "success")
        return redirect(url_for('library'))

    # For GET request, render the checkout page
    return render_template('checkout.html', cart=cart, total_price=total_price)

@app.route('/order_confirmation')
@login_required
def order_confirmation():
    return render_template("order_confirmation.html")

@app.route('/wishlist')
@login_required
def wishlist():
    return render_template('wishlist.html', games=current_user.wishlist)

@app.route('/wishlist/toggle/<int:game_id>', methods=['POST'])
@login_required
def toggle_wishlist(game_id):
    game = Game.query.get_or_404(game_id)

    if game in current_user.wishlist:
        current_user.wishlist.remove(game)
        db.session.commit()
        return jsonify({'wishlisted': False})
    else:
        current_user.wishlist.append(game)
        db.session.commit()
        return jsonify({'wishlisted': True})

@app.route('/mist_wallet')
def mist_wallet():
    return render_template('mist_wallet.html')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)


