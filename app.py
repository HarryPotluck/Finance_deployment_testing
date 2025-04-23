import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    cash = user[0]["cash"]
    unrealized = 0

    # Get stocks owned.
    stocks = db.execute(
        "SELECT symbol, SUM(CASE WHEN transaction_type = 'buy' THEN shares ELSE -shares END) AS shares FROM purchases WHERE user_id = ? GROUP BY symbol", session["user_id"])
    for stock in stocks:
        stock["current_price"] = lookup(stock["symbol"])["price"]
        unrealized += stock["shares"] * stock["current_price"]

    return render_template("index.html", username=user[0]["username"], stocks=stocks, balance=cash, unrealized=unrealized)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except ValueError:
            return apology("Only positive integers please")

        if not symbol or not lookup(symbol):
            return apology("Invalid symbol")
        if shares <= 0:
            return apology("Invalid shares input")

        price = lookup(symbol)["price"]
        capital = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        if (total_price := price*shares) > capital:
            return apology("Not enough money.")

        db.execute("INSERT INTO purchases (user_id, symbol, price, shares, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, price, shares, "buy")
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_price, session["user_id"])
        return redirect("/")
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
    history = db.execute(
        "SELECT transaction_type, symbol, price, shares, timestamp FROM purchases WHERE user_id = ?", session["user_id"])

    return render_template("history.html", username=user[0]["username"], history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Symbol plz...")

        stock = lookup(symbol)

        if stock is None:
            return apology("Sorry, invalid symbol")

        return render_template("quoted.html", stock=stock)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirmation")

        if not username:
            return apology("Please insert username!")
        if not password:
            return apology("Please insert password.")
        if not confirm:
            return apology("Please confirm your password")
        if password != confirm:
            return apology("Confirm password does not match! Please try again.")

        hashed_password = generate_password_hash(password)

        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, hashed_password)
        except ValueError:
            return apology("Username existed!")

        """Register success, so sent back to login"""

        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        try:
            shares = int(shares)
        except ValueError:
            return apology("Only positive integers please")

        if not symbol or not lookup(symbol):
            return apology("Invalid symbol")
        if shares <= 0:
            return apology("Invalid shares")

        # Calculate shares
        current_shares = db.execute(
            "SELECT SUM(CASE WHEN transaction_type = 'buy' THEN shares ELSE -shares END) AS shares FROM purchases WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)[0]['shares']

        if not current_shares:
            return apology("You've never bought this stock before.")
        if shares > current_shares:
            return apology(f'You only have {current_shares} shares')

        price = lookup(symbol)["price"]

        total_price = price*shares

        db.execute("INSERT INTO purchases (user_id, symbol, price, shares, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, price, shares, "sell")

        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_price, session["user_id"])

        return redirect("/")

    symbols = db.execute(
        "SELECT symbol FROM purchases WHERE user_id = ? GROUP BY symbol HAVING SUM(CASE WHEN transaction_type = 'buy' THEN shares ELSE -shares END) > 0", session["user_id"])

    return render_template("sell.html", symbols=symbols)
