import os
import re
import hashlib
import secrets
from contextlib import contextmanager
from getpass import getpass
from datetime import datetime

from dotenv import load_dotenv
import yfinance as yf
import mysql.connector as sql_con
from mysql.connector import errorcode

# -----------------------------
# Environment
# -----------------------------
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME_PREFIX = os.getenv("DB_NAME_PREFIX", "user_")  # e.g., user_nirali

# -----------------------------
# Helpers
# -----------------------------
def validate_username(username: str) -> str:
    if not username or not re.match(r"^[a-zA-Z0-9_]{3,30}$", username):
        raise ValueError("Username must be 3-30 characters (letters, numbers, underscores only)")
    return username.lower()

def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")
    return password

def validate_ticker(ticker: str) -> str:
    if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker.upper()):
        raise ValueError("Invalid ticker. Use 1-5 letters only")
    return ticker.upper()

def hash_password(password: str, salt: str | None = None):
    if salt is None:
        salt = secrets.token_hex(32)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return hashed == stored_hash

def db_name_for(username: str) -> str:
    # MySQL DB names: keep simple/alnum/underscore
    return f"{DB_NAME_PREFIX}{username}"

# -----------------------------
# DB Connections
# -----------------------------
def connect_server_only():
    """Connect to MySQL server without selecting a database."""
    try:
        return sql_con.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
    except sql_con.Error as e:
        raise ConnectionError(f"Failed to connect to MySQL server: {e}")

def ensure_user_database(username: str):
    """CREATE DATABASE if not exists for this user."""
    dbname = db_name_for(username)
    try:
        conn = connect_server_only()
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{dbname}` DEFAULT CHARACTER SET utf8mb4")
        cur.close()
        conn.close()
    except sql_con.Error as e:
        if getattr(e, "errno", None) in (errorcode.ER_DBACCESS_DENIED_ERROR, errorcode.ER_ACCESS_DENIED_ERROR):
            raise ConnectionError(
                f"No privilege to create database '{dbname}'. Ask admin to grant CREATE, or create manually."
            )
        raise ConnectionError(f"Failed to ensure database '{dbname}': {e}")

def connect_user_db(username: str):
    """Connect to the user's database (must exist)."""
    dbname = db_name_for(username)
    try:
        return sql_con.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=dbname)
    except sql_con.Error as e:
        raise ConnectionError(f"Failed to connect to database '{dbname}': {e}")

@contextmanager
def user_db_cursor(username: str, dictionary: bool = False):
    conn = None
    cur = None
    try:
        conn = connect_user_db(username)
        cur = conn.cursor(dictionary=dictionary)
        yield cur
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# -----------------------------
# Schema per user
# -----------------------------
def create_user_tables(username: str):
    """Create per-user schema (users + portfolios) inside that user's DB."""
    ensure_user_database(username)
    with user_db_cursor(username) as cursor:
        # Single-user users table (holds that user's auth row)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(30) UNIQUE NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP NULL,
                INDEX idx_username (username)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        # Portfolios table (no user_id needed in per-user DB)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ticker VARCHAR(5) NOT NULL,
                date DATE NOT NULL,
                open DECIMAL(10,2),
                close DECIMAL(10,2),
                volume BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_ticker_date (ticker, date),
                INDEX idx_ticker (ticker),
                INDEX idx_date (date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

# -----------------------------
# Auth (per user DB)
# -----------------------------
def register_user(username: str, password: str) -> bool:
    try:
        username = validate_username(username)
        password = validate_password(password)
        create_user_tables(username)  # ensures DB + tables

        pwd_hash, salt = hash_password(password)
        with user_db_cursor(username) as cursor:
            # If already has a row for this username, block re-register
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                print(f"Username '{username}' already exists (in their own DB).")
                return False

            cursor.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (%s, %s, %s)",
                (username, pwd_hash, salt)
            )
        print(f"User '{username}' registered successfully! (DB: {db_name_for(username)})")
        return True
    except ValueError as e:
        print(str(e))
        return False
    except Exception as e:
        print(f"Registration failed: {e}")
        return False

def login_user(username: str, password: str):
    """Return the username on success (we use username as identity)."""
    try:
        username = validate_username(username)
        # Try connecting to user's DB; if it doesn't exist, invalid login
        try:
            with user_db_cursor(username, dictionary=True) as cursor:
                cursor.execute("SELECT id, password_hash, salt FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                if not user or not verify_password(password, user["password_hash"], user["salt"]):
                    print("Invalid username or password")
                    return None

                cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))
                print(f"Welcome back, {username}! (DB: {db_name_for(username)})")
                return username
        except ConnectionError:
            # User DB missing => invalid login
            print("Invalid username or password")
            return None
    except ValueError as e:
        print(str(e))
        return None
    except Exception as e:
        print(f"Login failed: {e}")
        return None

# -----------------------------
# Portfolio ops (per user DB)
# -----------------------------
def add_stock(current_user: str, ticker: str):
    """Add last 5 days OHLCV for a ticker into this user's portfolios table."""
    try:
        ticker = validate_ticker(ticker)
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            print(f"No data found for ticker {ticker}. Please retry.")
            return False

        inserted = 0
        with user_db_cursor(current_user) as cursor:
            for date, row in hist.iterrows():
                cursor.execute("""
                    INSERT IGNORE INTO portfolios (ticker, date, open, close, volume)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    ticker,
                    date.date(),
                    round(float(row["Open"]), 2),
                    round(float(row["Close"]), 2),
                    int(row["Volume"])
                ))
                inserted += cursor.rowcount

        print(f"Added {inserted} days of data for {ticker}." if inserted else f"{ticker} data already exists.")
        return True
    except ValueError as e:
        print(f"Validation error: {e}")
        return False
    except Exception as e:
        print(f"Error adding stock: {e}")
        return False

def delete_stock(current_user: str, ticker: str):
    try:
        ticker = validate_ticker(ticker)
        with user_db_cursor(current_user) as cursor:
            cursor.execute("DELETE FROM portfolios WHERE ticker = %s", (ticker,))
            if cursor.rowcount:
                print(f"Deleted {cursor.rowcount} records for {ticker}")
                return True
            print(f"{ticker} not found in portfolio")
            return False
    except ValueError as e:
        print(f"Validation error: {e}")
        return False
    except Exception as e:
        print(f"Error deleting stock: {e}")
        return False

def display_portfolio(current_user: str):
    try:
        with user_db_cursor(current_user, dictionary=True) as cursor:
            # Get username
            cursor.execute("SELECT username FROM users LIMIT 1")
            urow = cursor.fetchone()
            username = urow["username"] if urow else current_user

            cursor.execute("""
                SELECT 
                    ticker,
                    MIN(date) AS first_date,
                    MAX(date) AS last_date,
                    COUNT(*) AS days,
                    AVG(close) AS avg_close,
                    MAX(close) AS max_close,
                    MIN(close) AS min_close
                FROM portfolios
                GROUP BY ticker
                ORDER BY ticker
            """)
            summary = cursor.fetchall()

        if not summary:
            print("Portfolio is empty")
            return

        print(f"\nPortfolio Summary for {username} (DB: {db_name_for(username)})")
        print("=" * 80)
        print(f"{'Ticker':<8} {'Days':<6} {'Avg Close':<12} {'Min Close':<12} "
              f"{'Max Close':<12} {'Date Range':<20}")
        print("-" * 80)
        for row in summary:
            date_range = f"{row['first_date']} to {row['last_date']}"
            print(f"{row['ticker']:<8} {row['days']:<6} "
                  f"${row['avg_close']:<11.2f} ${row['min_close']:<11.2f} "
                  f"${row['max_close']:<11.2f} {date_range:<20}")

        if input("\nView detailed data? (y/n): ").strip().lower() == "y":
            ticker = input("Enter ticker for details: ").strip().upper()
            display_stock_details(current_user, ticker)

    except Exception as e:
        print(f"Error displaying portfolio: {e}")

def display_stock_details(current_user: str, ticker: str):
    try:
        ticker = validate_ticker(ticker)
        with user_db_cursor(current_user, dictionary=True) as cursor:
            cursor.execute("""
                SELECT date, open, close, volume
                FROM portfolios
                WHERE ticker = %s
                ORDER BY date DESC
            """, (ticker,))
            rows = cursor.fetchall()

        if not rows:
            print(f"No data found for {ticker}")
            return

        print(f"\nDetailed data for {ticker}")
        print("=" * 70)
        print(f"{'Date':<12} {'Open':<10} {'Close':<10} {'Change':<14} {'Volume':<15}")
        print("-" * 70)
        for r in rows:
            change = (r["close"] or 0) - (r["open"] or 0)
            pct = (change / r["open"] * 100) if r["open"] else 0
            print(f"{str(r['date']):<12} ${r['open']:<9.2f} ${r['close']:<9.2f} "
                  f"{change:+.2f} ({pct:+.1f}%)   {r['volume']:>14,}")
    except ValueError as e:
        print(f"Validation error: {e}")
    except Exception as e:
        print(f"Error displaying details: {e}")

# -----------------------------
# Main
# -----------------------------
def main():
    print("Secure Portfolio Manager (Per-User Databases)")
    print("=" * 50)

    current_user = None  # store logged-in username

    while current_user is None:
        print("\n1. Login")
        print("2. Register")
        print("3. Exit")
        choice = input("\nChoose an option (1-3): ").strip()

        if choice == "1":
            username = input("Username: ").strip()
            password = getpass("Password: ")
            current_user = login_user(username, password)
        elif choice == "2":
            print("\nNew User Registration")
            print("Password requirements:\n- At least 8 characters\n- Upper & lower case\n- At least one number")
            username = input("\nChoose username: ").strip()
            password = getpass("Choose password: ")
            confirm = getpass("Confirm password: ")
            if password != confirm:
                print("Passwords don't match")
            else:
                if register_user(username, password):
                    print("Registration successful! You can now log in.")
        elif choice == "3":
            print("Goodbye!")
            return
        else:
            print("Invalid choice. Please retry.")

    # Authenticated menu
    while True:
        print(f"\n--- Portfolio Menu ({db_name_for(current_user)}) ---")
        print("1. Add a stock")
        print("2. Delete a stock")
        print("3. Display portfolio")
        print("4. Logout")

        c = input("\nEnter choice (1-4): ").strip()
        if c == "1":
            ticker = input("Enter ticker to add: ").strip()
            add_stock(current_user, ticker)
        elif c == "2":
            ticker = input("Enter ticker to delete: ").strip()
            delete_stock(current_user, ticker)
        elif c == "3":
            display_portfolio(current_user)
        elif c == "4":
            print("Logged out successfully! Enjoy!")
            break
        else:
            print("Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main()
