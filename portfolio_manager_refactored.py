import yfinance as yf # type: ignore
import pandas as pd
import mysql.connector as sql_con # type: ignore
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from contextlib import contextmanager
import os
import re
from dotenv import load_dotenv
from getpass import getpass
import hashlib
import secrets

# Load environment variables
load_dotenv()

# Note: Some of this code is modified for aesthetic purposes during CLI usage. 
# If any performance issues arise, please contact owners.

# TODO: Currently all Exceptions are handled by "crashing" output. Update as necessary.
# TODO: Users will be confused by table ID - update all instances to portfolio names and make `get_portfolio_id_by_name` - DONE
# TODO: Figure out indicators and/or LSTM use and adjust menu as necessary

# ==================== Database Connection ====================

def get_connection():
    """Create database connection using environment variables"""
    try:
        return sql_con.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME", "Lab3")
        )
    except sql_con.Error as e:
        raise ConnectionError(f"Failed to connect to database: {e}")

@contextmanager
def get_db_cursor(dictionary=False):
    """Context manager for database connections"""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=dictionary)
        yield cursor
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== Authentication ====================

def validate_username(username):
    """Validate username format"""
    if not username or not re.match("^[a-zA-Z0-9_]{3,30}$", username):
        raise ValueError("Username must be 3-30 characters (letters, numbers, underscores only)")
    return username.lower()

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")
    return password

# TODO: Check validity of hash functions; will assume it works
def hash_password(password, salt=None):
    """Hash password with salt"""
    if salt is None:
        salt = secrets.token_hex(32)
    password_salt = password + salt
    hashed = hashlib.sha256(password_salt.encode()).hexdigest()
    return hashed, salt

def verify_password(password, stored_hash, salt):
    """Verify password against hash"""
    hashed, _ = hash_password(password, salt)
    return hashed == stored_hash

def register_user(username, password):
    """Register new user"""
    try:
        username = validate_username(username)
        password = validate_password(password)
        password_hash, salt = hash_password(password)
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (username, password_hash, salt)
                VALUES (%s, %s, %s)
            """, (username, password_hash, salt))
            print(f"User '{username}' registered successfully!")
            return True
    except sql_con.IntegrityError:
        print(f"Username '{username}' already exists")
        return False
    except Exception as e:
        print(f"Registration failed: {e}")
        return False

def login_user(username, password):
    """Authenticate user and return user_id"""
    try:
        username = validate_username(username)
        
        with get_db_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, password_hash, salt 
                FROM users 
                WHERE username = %s
            """, (username,))
            
            user = cursor.fetchone()
            if not user or not verify_password(password, user['password_hash'], user['salt']):
                print("Invalid username or password")
                return None
            
            print(f"Welcome back, {username}!")
            return user['id']
    except Exception as e:
        print(f"Login failed: {e}")
        return None

# ==================== Data Validation ====================

def validate_ticker(ticker):
    """Validate ticker symbol format"""
    if not ticker or not re.match("^[A-Z]{1,5}$", ticker.upper()):
        raise ValueError(f"Invalid ticker '{ticker}'. Use 1-5 letters only")
    return ticker.upper()

def validate_date(date_str):
    """Validate and parse date string - interday use only"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD")

def validate_interval(interval):
    """Validate interval and determine data type"""
    valid_intervals = {
        'intraday': ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h'],
        'interday': ['1d', '5d', '1wk', '1mo', '3mo']
    }
    
    for data_type, intervals in valid_intervals.items():
        if interval in intervals:
            return data_type, interval
    
    raise ValueError(f"Invalid interval '{interval}'. Valid: {', '.join(sum(valid_intervals.values(), []))}")

# Note that this is only called when the user wants to call a portfolio. Refer `validate_date` otherwise
def validate_period(period):
    """Validate period for intraday data only"""
    # TODO: Slight logic error here I believe, valid_periods should only be up to 60d
    # Requires further testing; unavailable due to time constraints
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
    if period not in valid_periods:
        # Check if it's a number followed by 'd' (e.g., '30d', '60d')
        if not re.match(r'^\d{1,2}d$', period):
            raise ValueError(f"Invalid period '{period}'")
    
    # Check 60-day limit for intraday
    if re.match(r'^\d+d$', period):
        days = int(period[:-1])
        if days > 60:
            raise ValueError("Intraday data limited to 60 days maximum")
    
    return period

# ==================== DataFetcher Class ====================

class DataFetcher:
    """Handle yfinance data fetching with proper parameters"""
    # TODO: @staticmethod and/or class probably not needed here, but currently built/saved for modularity purposes
    # Change this in future lab.
    @staticmethod
    def fetch_data(tickers: List[str], data_type: str, **kwargs) -> pd.DataFrame:
        """
        Fetch data using yf.download() with appropriate parameters
        """
        try:

            if data_type == 'intraday':
                period = kwargs.get('period', '5d')
                interval = kwargs.get('interval', '1h')
                
                print(f"Fetching intraday data: {', '.join(tickers)} for {period} at {interval} intervals...")
                
                data = yf.download(
                    tickers,
                    period=period,
                    interval=interval,
                    ignore_tz=False,  # Keep timezone for intraday
                    group_by='ticker' if len(tickers) > 1 else 'column', # Default 'column'
                    auto_adjust=True,
                    prepost=False,
                    threads=True,
                    keepna=False,
                    progress=False
                )
                
            else:  # interday
                start = kwargs.get('start')
                end = kwargs.get('end', datetime.now().date())
                interval = kwargs.get('interval', '1d')
                
                print(f"Fetching interday data: {', '.join(tickers)} from {start} to {end} at {interval} intervals...")
                
                data = yf.download(
                    tickers,
                    start=start,
                    end=end,
                    interval=interval,
                    ignore_tz=True,   # Ignore timezone for daily+
                    group_by='ticker' if len(tickers) > 1 else 'column',
                    auto_adjust=True,
                    prepost=False,
                    threads=True,
                    keepna=False,
                    progress=False
                )
            
            if data.empty: # type: ignore - data will never be none I doubt; errors are caught by Exception
                raise ValueError("No data returned from yfinance")
            
            return data # type: ignore
            
        except Exception as e:
            raise Exception(f"Failed to fetch data: {e}")

# ==================== PortfolioManager Class ====================

class PortfolioManager:
    """Main portfolio management class"""
    
    def __init__(self):
        pass
    
    def create_portfolio(self, user_id: int, name: str, tickers: List[str], 
                        data_type: str, **kwargs) -> Optional[int]:
        """Create new portfolio with constraints"""
        try:
            # Validate inputs
            if not name or len(name) > 50:
                raise ValueError("Portfolio name must be 1-50 characters")
            
            validated_tickers = [validate_ticker(t) for t in tickers]
            
            # Prepare portfolio metadata
            interval = kwargs.get('interval')
            is_readonly = (data_type == 'intraday')
            
            with get_db_cursor() as cursor:
                # Create portfolio
                if data_type == 'intraday':
                    cursor.execute("""
                        INSERT INTO portfolios 
                        (user_id, name, data_type, period, interval_str, is_readonly)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (user_id, name, data_type, kwargs.get('period'), interval, is_readonly))
                else:  # interday
                    cursor.execute("""
                        INSERT INTO portfolios 
                        (user_id, name, data_type, start_date, end_date, interval_str, is_readonly)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, name, data_type, kwargs.get('start'), 
                          kwargs.get('end'), interval, is_readonly))
                
                portfolio_id = cursor.lastrowid
                
                # Add stocks to portfolio
                for ticker in validated_tickers:
                    cursor.execute("""
                        INSERT INTO portfolio_stocks (portfolio_id, ticker)
                        VALUES (%s, %s)
                    """, (portfolio_id, ticker))
                
                print(f"Portfolio '{name}' created successfully!")
                
                # Fetch initial data
                print("\nFetching initial data...")
                # Convert date objects to strings for yfinance
                fetch_kwargs = kwargs.copy()
                if 'start' in fetch_kwargs and hasattr(fetch_kwargs['start'], 'strftime'):
                    fetch_kwargs['start'] = fetch_kwargs['start'].strftime('%Y-%m-%d')
                if 'end' in fetch_kwargs and hasattr(fetch_kwargs['end'], 'strftime'):
                    fetch_kwargs['end'] = fetch_kwargs['end'].strftime('%Y-%m-%d')
                
                data = DataFetcher.fetch_data(validated_tickers, data_type, **fetch_kwargs)
                print(f"Retrieved {len(data)} data points")
                
                return portfolio_id

        # Specific error for repeated usernames        
        except sql_con.IntegrityError:
            print(f"Portfolio name '{name}' already exists for this user")
            return None
        except Exception as e:
            print(f"Failed to create portfolio: {e}")
            return None
    
    def list_portfolios(self, user_id: int):
        """Display simple list of portfolios for a user"""
        try:
            with get_db_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT id, name
                    FROM portfolios 
                    WHERE user_id = %s
                    ORDER BY last_edited_at DESC
                """, (user_id,))
                
                portfolios = cursor.fetchall()
                
                if not portfolios:
                    print("No portfolios found")
                    return
                
                print("\nYour Portfolios:")
                for i, p in enumerate(portfolios, 1):
                    print(f"[{i}] {p['name']}")
                
        except Exception as e:
            print(f"Error listing portfolios: {e}")
    
    def show_portfolio_summary(self, portfolio_name: str, user_id: int):
        """Show current portfolio summary with holdings"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return
            
        try:
            with get_db_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT p.data_type, p.interval_str, p.start_date, p.end_date, p.period, p.is_readonly,
                           COUNT(ps.ticker) as stock_count,
                           GROUP_CONCAT(ps.ticker ORDER BY ps.ticker) as tickers
                    FROM portfolios p
                    LEFT JOIN portfolio_stocks ps ON p.id = ps.portfolio_id
                    WHERE p.id = %s
                    GROUP BY p.id
                """, (portfolio_id,))
                
                portfolio = cursor.fetchone()
                if not portfolio:
                    print("Portfolio not found")
                    return
                
                print(f"\n" + "=" * 60)
                print(f"         PORTFOLIO: {portfolio_name.upper()}")
                print("=" * 60)
                print(f"Type: {portfolio['data_type'].upper()} | Interval: {portfolio['interval_str']}")
                
                if portfolio['data_type'] == 'intraday':
                    print(f"Period: {portfolio['period']} | Read-only: Yes")
                else:
                    print(f"Date Range: {portfolio['start_date']} to {portfolio['end_date']}")
                    print(f"Read-only: {'Yes' if portfolio['is_readonly'] else 'No'}")
                
                print(f"\nCurrent Holdings ({portfolio['stock_count']} stocks):")
                if portfolio['tickers']:
                    tickers = portfolio['tickers'].split(',')
                    ticker_display = ', '.join(tickers)
                    print(f"  {ticker_display}")
                else:
                    print("  No stocks in portfolio")
                print("=" * 60)
                
        except Exception as e:
            print(f"Error displaying portfolio summary: {e}")
    
    def get_portfolio_data(self, portfolio_name: str, user_id: int) -> Optional[pd.DataFrame]:
        """Fetch current data for all stocks in portfolio"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return None
            
        try:
            with get_db_cursor(dictionary=True) as cursor:
                # Get portfolio details and verify ownership
                cursor.execute("""
                    SELECT p.*, GROUP_CONCAT(ps.ticker) as tickers
                    FROM portfolios p
                    LEFT JOIN portfolio_stocks ps ON p.id = ps.portfolio_id
                    WHERE p.id = %s AND p.user_id = %s
                    GROUP BY p.id
                """, (portfolio_id, user_id))
                
                portfolio = cursor.fetchone()
                
                if not portfolio:
                    print("Portfolio not found or access denied")
                    return None
                
                if not portfolio['tickers']:
                    print("Portfolio has no stocks")
                    return None
                
                # Prepare fetch parameters
                tickers = portfolio['tickers'].split(',')
                kwargs = {
                    'interval': portfolio['interval_str']
                }
                
                if portfolio['data_type'] == 'intraday':
                    kwargs['period'] = portfolio['period']
                else:
                    # Convert date objects to strings for yfinance
                    kwargs['start'] = portfolio['start_date'].strftime('%Y-%m-%d')
                    kwargs['end'] = portfolio['end_date'].strftime('%Y-%m-%d')
                
                # Fetch data
                data = DataFetcher.fetch_data(
                    tickers, 
                    portfolio['data_type'], 
                    **kwargs
                )
                
                return data
                
        except Exception as e:
            print(f"Error fetching portfolio data: {e}")
            return None
    
    def add_stocks(self, portfolio_name: str, user_id: int, tickers: List[str]) -> bool:
        """Add stocks to existing interday portfolio"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return False
            
        try:
            with get_db_cursor(dictionary=True) as cursor:
                # Check portfolio exists and is not readonly
                cursor.execute("""
                    SELECT data_type, is_readonly 
                    FROM portfolios 
                    WHERE id = %s AND user_id = %s
                """, (portfolio_id, user_id))
                
                portfolio = cursor.fetchone()
                if not portfolio:
                    print("Portfolio not found or access denied")
                    return False
                
                elif portfolio['is_readonly']:
                    print("Cannot modify read-only portfolio (intraday portfolios are read-only)")
                    return False
                
                # Add stocks
                validated_tickers = [validate_ticker(t) for t in tickers]
                added = 0
                
                for ticker in validated_tickers:
                    try:
                        cursor.execute("""
                            INSERT INTO portfolio_stocks (portfolio_id, ticker)
                            VALUES (%s, %s)
                        """, (portfolio_id, ticker))
                        added += 1
                        print(f"Added {ticker}")
                    except sql_con.IntegrityError:
                        print(f"{ticker} already in portfolio")
                
                if added > 0:
                    print(f"Successfully added {added} stock(s)")
                    return True
                
                return False
                
        except Exception as e:
            print(f"Error adding stocks: {e}")
            return False
    
    def remove_stocks(self, portfolio_name: str, user_id: int, tickers: List[str]) -> bool:
        """Remove stocks from portfolio"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return False
            
        try:
            with get_db_cursor() as cursor:
                # Verify ownership
                cursor.execute("""
                    SELECT 1 FROM portfolios 
                    WHERE id = %s AND user_id = %s
                """, (portfolio_id, user_id))
                
                if not cursor.fetchone():
                    print("Portfolio not found or access denied")
                    return False
                
                # Remove stocks
                validated_tickers = [validate_ticker(t) for t in tickers]
                removed = 0
                
                for ticker in validated_tickers:
                    cursor.execute("""
                        DELETE FROM portfolio_stocks 
                        WHERE portfolio_id = %s AND ticker = %s
                    """, (portfolio_id, ticker))
                    
                    if cursor.rowcount > 0:
                        removed += 1
                        print(f"Removed {ticker}")
                    else:
                        print(f"{ticker} not found in portfolio")
                
                if removed > 0:
                    print(f"Successfully removed {removed} stock(s)")
                    return True
                
                return False
                
        except Exception as e:
            print(f"Error removing stocks: {e}")
            return False
    
    def update_interval(self, portfolio_name: str, user_id: int, start_date: str, end_date: str) -> bool:
        """Update date range for interday portfolio and refetch data"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return False
            
        try:
            with get_db_cursor(dictionary=True) as cursor:
                # Check portfolio exists, is interday, and user owns it
                cursor.execute("""
                    SELECT data_type, is_readonly, name, interval_str,
                           GROUP_CONCAT(ps.ticker) as tickers
                    FROM portfolios p
                    LEFT JOIN portfolio_stocks ps ON p.id = ps.portfolio_id
                    WHERE p.id = %s AND p.user_id = %s
                    GROUP BY p.id
                """, (portfolio_id, user_id))
                
                portfolio = cursor.fetchone()
                if not portfolio:
                    print("Portfolio not found or access denied")
                    return False
                
                if portfolio['data_type'] == 'intraday':
                    print("Cannot update date range for intraday portfolios (they are read-only)")
                    return False
                
                if portfolio['is_readonly']:
                    print("Cannot update read-only portfolio")
                    return False
                
                # Validate dates
                start_dt = validate_date(start_date)
                end_dt = validate_date(end_date)
                
                if start_dt >= end_dt:
                    print("Start date must be before end date")
                    return False
                
                if end_dt > datetime.now().date():
                    print("End date cannot be in the future")
                    return False
                
                # Update portfolio dates
                cursor.execute("""
                    UPDATE portfolios 
                    SET start_date = %s, end_date = %s
                    WHERE id = %s
                """, (start_dt, end_dt, portfolio_id))
                
                print(f"Updated portfolio '{portfolio['name']}' date range to {start_dt} - {end_dt}")
                
                # Refetch data if portfolio has stocks
                if portfolio['tickers']:
                    print("\nRefetching data with new date range...")
                    tickers = portfolio['tickers'].split(',')
                    
                    try:
                        data = DataFetcher.fetch_data(
                            tickers, 
                            'interday',
                            start=start_dt.strftime('%Y-%m-%d'),
                            end=end_dt.strftime('%Y-%m-%d'),
                            interval=portfolio['interval_str']
                        )
                        print(f"Successfully retrieved {len(data)} data points")
                    except Exception as e:
                        print(f"Warning: Could not fetch data with new date range: {e}")
                        print("Portfolio dates updated but data may be unavailable")
                
                return True
                
        except ValueError as e:
            print(f"Invalid input: {e}")
            return False
        except Exception as e:
            print(f"Error updating portfolio: {e}")
            return False
    
    def check_args(self, portfolio_name: str, user_id: int) -> None:
        """Display detailed portfolio info for user decision-making"""
        portfolio_id = self.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            return
            
        try:
            with get_db_cursor(dictionary=True) as cursor:
                # Get portfolio details
                cursor.execute("""
                    SELECT p.*, u.username,
                           COUNT(ps.ticker) as stock_count,
                           GROUP_CONCAT(ps.ticker ORDER BY ps.ticker) as tickers,
                           GROUP_CONCAT(ps.added_at ORDER BY ps.ticker) as added_dates
                    FROM portfolios p
                    JOIN users u ON p.user_id = u.id
                    LEFT JOIN portfolio_stocks ps ON p.id = ps.portfolio_id
                    WHERE p.id = %s AND p.user_id = %s
                    GROUP BY p.id
                """, (portfolio_id, user_id))
                
                portfolio = cursor.fetchone()
                if not portfolio:
                    print("Portfolio not found or access denied")
                    return
                
                # Display comprehensive portfolio information
                print("\n" + "═" * 80)
                print(f"         PORTFOLIO INFORMATION - ID: {portfolio['id']}")
                print("═" * 80)
                
                print(f"Portfolio Name: {portfolio['name']}")
                print(f"Owner: {portfolio['username']}")
                print(f"Created: {portfolio['created_at']}")
                print(f"Last Modified: {portfolio['last_edited_at']}")
                print(f"Data Type: {portfolio['data_type'].upper()}")
                print(f"Interval: {portfolio['interval_str']}")
                
                # Time range information
                if portfolio['data_type'] == 'intraday':
                    print(f"Period: {portfolio['period']}")
                    print(f"Read-only: Yes (intraday portfolios cannot be modified)")
                else:
                    print(f"Date Range: {portfolio['start_date']} to {portfolio['end_date']}")
                    days = (portfolio['end_date'] - portfolio['start_date']).days
                    print(f"Duration: {days} days")
                    print(f"Read-only: {'Yes' if portfolio['is_readonly'] else 'No'}")
                
                # Stock information
                print("\n" + "─" * 80)
                print(f"HOLDINGS ({portfolio['stock_count']} stocks)")
                print("─" * 80)
                
                if portfolio['tickers']:
                    tickers = portfolio['tickers'].split(',')
                    added_dates = portfolio['added_dates'].split(',')
                    
                    print(f"{'Ticker':<8} {'Added Date':<12} {'Status':<10}")
                    print("─" * 35)
                    
                    for ticker, added_date in zip(tickers, added_dates):
                        status = "Active"
                        print(f"{ticker:<8} {added_date.split()[0]:<12} {status:<10}")
                else:
                    print("No stocks in portfolio")
                
                # Available operations
                print("\n" + "─" * 80)
                print("AVAILABLE OPERATIONS")
                print("─" * 80)
                
                if portfolio['data_type'] == 'intraday':
                    print("View portfolio data")
                    print("Remove stocks (removes from portfolio but data stays read-only)")
                    print("Cannot add stocks (intraday portfolios are read-only)")
                    print("Cannot modify date range (intraday portfolios are read-only)")
                else:
                    print("View portfolio data")
                    print("Add new stocks")
                    print("Remove stocks")
                    if not portfolio['is_readonly']:
                        print("Update date range (will refetch all data)")
                    else:
                        print("Cannot modify (portfolio is marked read-only)")
                
                # Data constraints
                print("\n" + "─" * 80)
                print("DATA CONSTRAINTS")
                print("─" * 80)
                
                if portfolio['data_type'] == 'intraday':
                    print("Intraday data limited to last 60 days maximum")
                    print("High-frequency data (minutes/hours)")
                    print("Portfolio becomes read-only after creation")
                else:
                    print("No date range limitations")
                    print("Daily or longer intervals")
                    print("Fully modifiable (add/remove stocks, change dates)")
                
                print("\n" + "═" * 80)
                
        except Exception as e:
            print(f"Error displaying portfolio info: {e}")
    
    def get_portfolio_id_by_name(self, user_id: int, portfolio_name: str) -> Optional[int]:
        """Get portfolio ID by name for a specific user"""
        try:
            with get_db_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT id FROM portfolios 
                    WHERE user_id = %s AND name = %s
                """, (user_id, portfolio_name))
                
                result = cursor.fetchone()
                return result['id'] if result else None
        except Exception:
            return None
    
    def display_portfolio_data(self, portfolio_name: str, user_id: int):
        """Display portfolio data with formatting"""
        data = self.get_portfolio_data(portfolio_name, user_id)
        
        if data is None or data.empty:
            return
        
        print("\nPortfolio Data Summary:")
        print("=" * 80)
        
        # Handle both single and multiple ticker formats
        if isinstance(data.columns, pd.MultiIndex):
            # Multiple tickers
            for ticker in data.columns.get_level_values(0).unique():
                ticker_data = data[ticker]
                if 'Close' in ticker_data.columns:
                    latest = ticker_data.iloc[-1]
                    print(f"\n{ticker}:")
                    print(f"  Latest Close: ${latest['Close']:.2f}")
                    if 'Adj Close' in ticker_data.columns:
                        print(f"  Latest Adj Close: ${latest['Adj Close']:.2f}")
                    print(f"  High: ${ticker_data['High'].max():.2f}")
                    print(f"  Low: ${ticker_data['Low'].min():.2f}")
                    print(f"  Avg Volume: {ticker_data['Volume'].mean():,.0f}")
        else:
            # Single ticker
            if 'Close' in data.columns:
                latest = data.iloc[-1]
                print(f"Latest Close: ${latest['Close']:.2f}")
                if 'Adj Close' in data.columns:
                    print(f"Latest Adj Close: ${latest['Adj Close']:.2f}")
                print(f"High: ${data['High'].max():.2f}")
                print(f"Low: ${data['Low'].min():.2f}")
                print(f"Avg Volume: {data['Volume'].mean():,.0f}")
        
        print(f"\nData Points: {len(data)}")
        print(f"Date Range: {data.index[0]} to {data.index[-1]}")
        
        # Offer detailed view
        detail_choice = input("\nView detailed recent data? (y/n): ").strip().lower()
        if detail_choice == 'y':
            print(f"\nDetailed Recent Data (Last 10 entries):")
            print("-" * 110)
            print(f"{'Date':<12} {'Open':<8} {'High':<8} {'Low':<8} {'Close':<8} {'Adj Close':<10} {'Volume':<12} {'Change':<8}")
            print("-" * 110)
            
            recent_data = data.tail(10) if len(data) > 10 else data
            
            # Handle both single and multi-ticker data
            if isinstance(data.columns, pd.MultiIndex):
                # Ask which ticker to show in detail
                tickers = data.columns.get_level_values(0).unique().tolist()
                print(f"Available tickers: {', '.join(tickers)}")
                ticker_choice = input("Enter ticker for detailed view: ").strip().upper()
                if ticker_choice in tickers:
                    ticker_data = recent_data[ticker_choice]
                    self._show_detailed_table(ticker_data)
            else:
                # Single ticker
                self._show_detailed_table(recent_data)
    
    def _show_detailed_table(self, data):
        """Show detailed OHLCV+Adj Close table"""
        for idx, row in data.iterrows():
            if 'Close' in row and 'Open' in row:
                daily_change = ((row['Close'] - row['Open']) / row['Open']) * 100
                date_str = str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10]
                
                adj_close = row.get('Adj Close', row['Close'])  # Fallback if missing
                
                print(f"{date_str:<12} "
                      f"${row['Open']:<7.2f} "
                      f"${row['High']:<7.2f} "
                      f"${row['Low']:<7.2f} "
                      f"${row['Close']:<7.2f} "
                      f"${adj_close:<9.2f} "
                      f"{row['Volume']:>11,.0f} "
                      f"{daily_change:+6.2f}%")
        print("-" * 110)
        
        # Show simple performance metrics
        if isinstance(data.columns, pd.MultiIndex):
            # Multiple tickers - show portfolio overview
            total_avg_volume = 0
            for ticker in data.columns.get_level_values(0).unique():
                ticker_data = data[ticker]
                if 'Volume' in ticker_data.columns:
                    total_avg_volume += ticker_data['Volume'].mean()
            print(f"Total Avg Daily Volume: {total_avg_volume:,.0f}")
        else:
            # Single ticker - show performance
            if 'Close' in data.columns:
                start_price = data['Close'].iloc[0]
                end_price = data['Close'].iloc[-1]
                total_return = ((end_price - start_price) / start_price) * 100
                print(f"Total Return: {total_return:+.2f}%")

# ==================== Database Setup ====================

def create_tables():
    """Create all required tables and handle migrations"""
    with get_db_cursor() as cursor:
        # Check if last_edited_at column exists, add it if missing
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'portfolios' 
            AND COLUMN_NAME = 'last_edited_at'
        """)
        
        result = cursor.fetchone()
        if result and result[0] == 0:
            print("Adding last_edited_at column to existing portfolios table...")
            cursor.execute("""
                ALTER TABLE portfolios 
                ADD COLUMN last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            """)
            print("Column added successfully!")
    
    with get_db_cursor() as cursor:
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(30) UNIQUE NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Portfolios table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(50) NOT NULL,
                data_type ENUM('intraday', 'interday') NOT NULL,
                start_date DATE,
                end_date DATE,
                period VARCHAR(10),
                interval_str VARCHAR(10) NOT NULL,
                is_readonly BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE KEY unique_user_portfolio (user_id, name)
            )
        """)
        
        # Portfolio stocks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_stocks (
                portfolio_id INT NOT NULL,
                ticker VARCHAR(5) NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (portfolio_id, ticker),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
            )
        """)

# ==================== CLI Interface ====================

def get_help_text(context='main'):
    """Get context-sensitive help text"""
    help_texts = {
        'main': """
╔══════════════════════════════════════════════════════════════════╗
║                    PORTFOLIO MANAGER HELP                        ║
╠══════════════════════════════════════════════════════════════════╣
║ Commands available at any prompt:                                ║
║   help, ?  - Show context-sensitive help                         ║
║   back     - Return to previous menu                             ║
║   exit     - Exit the program                                    ║
║                                                                  ║
║ Portfolio Types:                                                 ║
║ • Intraday: High-frequency data (1m-1h), max 60 days, read-only  ║
║ • Interday: Daily+ data (1d-3mo), flexible dates, modifiable     ║
║                                                                  ║
║ Main Menu Options:                                               ║
║ 1. Create Portfolio - Set up new portfolio with stocks           ║
║ 2. View Portfolios - List all your portfolios                    ║
║ 3. Display Data - Show portfolio performance and holdings        ║
║ 4. Add Stocks - Add tickers to interday portfolios               ║
║ 5. Remove Stocks - Remove tickers from portfolios                ║
║ 6. Update Dates - Change date range (interday only)              ║
║ 7. Portfolio Info - Detailed portfolio information               ║
╚══════════════════════════════════════════════════════════════════╝
""",
        
        'create': """
╔══════════════════════════════════════════════════════════════════╗
║                  CREATE PORTFOLIO HELP                           ║
╠══════════════════════════════════════════════════════════════════╣
║ Portfolio Creation Flow:                                         ║
║ 1. Name: Choose a descriptive name (1-50 chars)                  ║
║ 2. Tickers: Enter stock symbols separated by commas              ║
║    Example: AAPL, MSFT, GOOGL                                    ║
║ 3. Interval: Choose data frequency                               ║
║    • Intraday: 1m, 2m, 5m, 15m, 30m, 1h                          ║
║    • Interday: 1d, 5d, 1wk, 1mo, 3mo                             ║
║ 4. Time Range:                                                   ║
║    • Intraday: Period only ('1d' to '90d')                       ║
║    • Interday: Start and end dates (YYYY-MM-DD)                  ║
╚══════════════════════════════════════════════════════════════════╝
""",
        
        'interval': """
╔══════════════════════════════════════════════════════════════════╗
║                    INTERVAL HELP                                 ║
╠══════════════════════════════════════════════════════════════════╣
║ Intraday Intervals (Read-only portfolios):                       ║
║   1m  - 1 minute bars    15m - 15 minute bars                    ║
║   2m  - 2 minute bars    30m - 30 minute bars                    ║
║   5m  - 5 minute bars    1h  - 1 hour bars                       ║
║                                                                  ║
║ Interday Intervals (Modifiable portfolios):                      ║
║   1d  - Daily bars       1wk - Weekly bars                       ║
║   5d  - 5 day bars       1mo - Monthly bars                      ║
║   3mo - 3 month bars                                             ║
║                                                                  ║
║ Note: Intraday data is limited to last 60 days                   ║
╚══════════════════════════════════════════════════════════════════╝
""",
        
        'period': """
╔══════════════════════════════════════════════════════════════════╗
║                     PERIOD HELP                                  ║
╠══════════════════════════════════════════════════════════════════╣
║ Valid periods for intraday data:                                 ║
║   1d  - 1 day           1mo - 1 month                            ║
║   5d  - 5 days          3mo - 3 months                           ║
║   Custom: 1-60 followed by 'd' (e.g., 30d, 45d)                  ║
║                                                                  ║
║ Examples:                                                        ║
║   5d   - Last 5 days of intraday data                            ║
║   30d  - Last 30 days of intraday data                           ║
║   60d  - Maximum allowed (60 days)                               ║
╚══════════════════════════════════════════════════════════════════╝
"""
    }
    return help_texts.get(context, help_texts['main'])

def show_help(context='main'):
    """Display help and wait for user to continue"""
    print(get_help_text(context))
    input("\nPress Enter to continue...")

def check_help_command(user_input, context='main'):
    """Check if user requested help and show it"""
    if user_input.lower() in ['help', '?']:
        show_help(context)
        return True
    return False

def manage_portfolio_flow(user_id: int, pm: PortfolioManager):
    """Flow for selecting and managing a specific portfolio"""
    while True:
        pm.list_portfolios(user_id)
        portfolio_name = input("\nEnter portfolio name to manage (or 'back'): ").strip()
        
        if portfolio_name.lower() == 'back':
            return
        
        if check_help_command(portfolio_name):
            continue
            
        if not portfolio_name:
            print("Portfolio name cannot be empty")
            continue
        
        # Check if portfolio exists and get its info
        portfolio_id = pm.get_portfolio_id_by_name(user_id, portfolio_name)
        if not portfolio_id:
            print(f"Portfolio '{portfolio_name}' not found")
            continue
        
        # Show current portfolio status
        pm.show_portfolio_summary(portfolio_name, user_id)
        
        # Portfolio management menu
        while True:
            print(f"\n--- Managing: {portfolio_name} ---")
            print("1. View detailed stock data")
            print("2. Add stocks")
            print("3. Remove stocks")
            print("4. Update date range (interday only)")
            print("5. Portfolio information")
            print("0. Back to portfolio selection")
            
            sub_choice = input("\nEnter choice (0-5): ").strip()
            
            if sub_choice == "1":
                pm.display_portfolio_data(portfolio_name, user_id)
                
            elif sub_choice == "2":
                ticker_input = input("\nEnter ticker(s) to add (comma-separated): ").strip().upper()
                if ticker_input:
                    tickers = [t.strip() for t in ticker_input.split(',')]
                    if pm.add_stocks(portfolio_name, user_id, tickers):
                        pm.show_portfolio_summary(portfolio_name, user_id)  # Refresh display
                
            elif sub_choice == "3":
                ticker_input = input("\nEnter ticker(s) to remove (comma-separated): ").strip().upper()
                if ticker_input:
                    tickers = [t.strip() for t in ticker_input.split(',')]
                    if pm.remove_stocks(portfolio_name, user_id, tickers):
                        pm.show_portfolio_summary(portfolio_name, user_id)  # Refresh display
                
            elif sub_choice == "4":
                start_date = input("\nEnter new start date (YYYY-MM-DD): ").strip()
                end_date = input("Enter new end date (YYYY-MM-DD): ").strip()
                if start_date and end_date:
                    if pm.update_interval(portfolio_name, user_id, start_date, end_date):
                        pm.show_portfolio_summary(portfolio_name, user_id)  # Refresh display
                
            elif sub_choice == "5":
                pm.check_args(portfolio_name, user_id)
                
            elif sub_choice == "0":
                break
                
            else:
                print("Invalid choice. Please enter 0-5.")
        
        # After exiting portfolio management, ask if they want to select another
        continue_choice = input("\nManage another portfolio? (y/n): ").strip().lower()
        if continue_choice != 'y':
            break

def portfolio_creation_flow(user_id: int, pm: PortfolioManager):
    """Sequential flow for creating a portfolio"""
    try:
        # Step 1: Portfolio name
        while True:
            name = input("\nEnter portfolio name (or 'help'): ").strip()
            if check_help_command(name, 'create'):
                continue
            if not name:
                print("Portfolio name cannot be empty")
                continue
            break
        
        # Step 2: Tickers
        while True:
            ticker_input = input("Enter ticker(s) separated by commas (or 'help'): ").strip()
            if check_help_command(ticker_input, 'create'):
                continue
            ticker_input = ticker_input.upper()
            if not ticker_input:
                print("At least one ticker is required")
                continue
            tickers = [t.strip() for t in ticker_input.split(',')]
            break
        
        # Step 3: Interval
        print("\nAvailable intervals:")
        print("Intraday: 1m, 2m, 5m, 15m, 30m, 1h")
        print("Interday: 1d, 5d, 1wk, 1mo, 3mo")
        
        while True:
            interval = input("\nEnter interval (or 'help'): ").strip().lower()
            if check_help_command(interval, 'interval'):
                print("\nAvailable intervals:")
                print("Intraday: 1m, 2m, 5m, 15m, 30m, 1h")
                print("Interday: 1d, 5d, 1wk, 1mo, 3mo")
                continue
            try:
                data_type, interval = validate_interval(interval)
                break
            except ValueError as e:
                print(f"Invalid interval: {e}")
                continue
        
        # Step 4: Branch based on data type
        kwargs = {'interval': interval}
        
        if data_type == 'intraday':
            print("\nIntraday portfolio (read-only after creation)")
            while True:
                period = input("Enter period ('1d' to '60d') or 'help': ").strip()
                if check_help_command(period, 'period'):
                    continue
                try:
                    kwargs['period'] = validate_period(period)
                    break
                except ValueError as e:
                    print(f"Invalid period: {e}")
                    continue
        else:
            print("\nInterday portfolio (can be modified later)")
            while True:
                start_str = input("Enter start date (YYYY-MM-DD) or 'help': ").strip()
                if check_help_command(start_str, 'create'):
                    continue
                try:
                    kwargs['start'] = validate_date(start_str) # type: ignore
                    break
                except ValueError as e:
                    print(f"Invalid date: {e}")
                    continue
            
            while True:
                end_str = input("Enter end date (YYYY-MM-DD) or press Enter for today: ").strip()
                if not end_str:
                    kwargs['end'] = datetime.now().date() # type: ignore
                    break
                if check_help_command(end_str, 'create'):
                    continue
                try:
                    kwargs['end'] = validate_date(end_str) # type: ignore
                    break
                except ValueError as e:
                    print(f"Invalid date: {e}")
                    continue
            
            if kwargs['start'] >= kwargs['end']:
                print("Start date must be before end date")
                return
        
        # Create portfolio
        portfolio_id = pm.create_portfolio(user_id, name, tickers, data_type, **kwargs)
        
        if portfolio_id:
            print(f"\nPortfolio created with ID: {portfolio_id}")
            
    except ValueError as e:
        print(f"Invalid input: {e}")
    except Exception as e:
        print(f"Error creating portfolio: {e}")

def main():
    """Main application loop"""
    print("Portfolio Manager - Refactored Version")
    print("=" * 50)
    
    # Initialize
    try:
        print("Connecting to database...")
        create_tables()
        pm = PortfolioManager()
    except Exception as e:
        print(f"Database error: {e}")
        print("\nPlease ensure your .env file is configured correctly")
        return
    
    # Authentication loop
    user_id = None
    while user_id is None:
        print("\n1. Login")
        print("2. Register")
        print("0. Exit")
        
        choice = input("\nChoose an option (0-2, or 'help'): ").strip()
        
        if check_help_command(choice):
            continue
        
        if choice == "1":
            username = input("Username: ").strip()
            password = getpass("Password: ")
            user_id = login_user(username, password)
            
        elif choice == "2":
            print("\nNew User Registration")
            print("Password requirements:")
            print("- At least 8 characters")
            print("- Include uppercase and lowercase letters")
            print("- Include at least one number")
            
            username = input("\nChoose username: ").strip()
            password = getpass("Choose password: ")
            confirm = getpass("Confirm password: ")
            
            if password != confirm:
                print("Passwords don't match")
            else:
                register_user(username, password)
                
        elif choice == "3":
            print("Goodbye!")
            return
        else:
            print("Invalid choice")
    
    # Main menu loop
    while True:
        print("\n--- Portfolio Manager ---")
        print("1. Create new portfolio")
        print("2. View all portfolios")
        print("3. Select and manage portfolio")
        print("0. Logout")
        
        choice = input("\nEnter choice (0-3, or 'help'): ").strip()
        
        if check_help_command(choice, 'main'):
            continue
        
        if choice == "1":
            portfolio_creation_flow(user_id, pm)
            
        elif choice == "2":
            pm.list_portfolios(user_id)
            
        elif choice == "3":
            manage_portfolio_flow(user_id, pm)
                
        elif choice == "0":
            print("Logged out successfully!")
            break
        else:
            print("Invalid choice. Please enter 0-3 or 'help'.")

if __name__ == "__main__":
    main()