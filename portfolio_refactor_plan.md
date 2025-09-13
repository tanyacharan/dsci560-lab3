# Portfolio Manager Refactor - Handoff for Future Reference

## Overview
Refactor existing single-table portfolio manager to support:
- Separate portfolios with different data types (intraday vs interday)
- Per-portfolio constraints and metadata
- On-demand data fetching using yf.download()
- Proper database normalization

## Database Schema

```sql
-- Users table
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(30) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolios table  
CREATE TABLE portfolios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(50) NOT NULL,
    data_type ENUM('intraday', 'interday') NOT NULL,
    start_date DATE,              -- for interday only
    end_date DATE,                -- for interday only  
    period VARCHAR(10),           -- for intraday only (e.g., '60d')
    interval_str VARCHAR(10) NOT NULL,  -- '1d', '1h', '5m', etc.
    is_readonly BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE KEY unique_user_portfolio (user_id, name)
);

-- Portfolio stocks (many-to-many)
CREATE TABLE portfolio_stocks (
    portfolio_id INT NOT NULL,
    ticker VARCHAR(5) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (portfolio_id, ticker),
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
);

-- Stock data cache (optional - implement if performance needed)
CREATE TABLE stock_data_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(5) NOT NULL,
    date_time DATETIME NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4), 
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    adj_close DECIMAL(12, 4),
    volume BIGINT,
    interval_str VARCHAR(10) NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_ticker_datetime_interval (ticker, date_time, interval_str),
    INDEX idx_ticker_interval (ticker, interval_str),
    INDEX idx_datetime (date_time)
);
```

## Implementation Tasks for Future Versions

**PRIORITY: Focus ONLY on core functionality and database migration for now.**
**Hold off on advanced features, comprehensive testing, and optimization until core works.**

### 1. Database Migration (PRIORITY)
- [ ] Create migration script from current single table to new schema
- [ ] Add foreign key constraints
- [ ] Create indexes for performance
- [ ] Handle existing data migration

### 2. Core Functionality (PRIORITY)
- [ ] Implement PortfolioManager.create_portfolio()
- [ ] Implement DataFetcher.fetch_data() with proper yf.download() params
- [ ] Add validation for intraday 60-day limit
- [ ] Implement portfolio stock management (add/remove)

### 3. Sequential CLI Interface (PRIORITY)
- [ ] Sequential input flow: ticker → period → branch to intraday/interday
- [ ] Simple portfolio creation workflow
- [ ] Basic display functions for new schema

**CLI Flow Design:**
```
1. Ask for portfolio name
2. Ask for ticker(s) (comma-separated)
3. Ask for period/interval
4. Based on interval, automatically determine intraday vs interday:
   - If `interval in ['1m', '2m', '5m', '15m', '30m', '60m', '1h']` → intraday flow
   - If `interval in ['1d', '5d', '1wk', '1mo']` → interday flow
5. For intraday: period only (auto-readonly)
6. For interday: ask for start_date, end_date
7. Create portfolio and fetch initial data
```

### 4. Data Processing (HOLD OFF)
- [ ] Implement DataProcessor methods for returns calculation
- [ ] Add moving averages, volatility calculations
- [ ] Handle timezone issues between intraday/interday data

### 5. Error Handling & Validation (HOLD OFF - basic only)
- [ ] Basic yfinance parameter validation
- [ ] Essential input validation only

### 6. Testing (HOLD OFF)
- [ ] Unit tests for each class
- [ ] Integration tests with live yfinance data
- [ ] Test edge cases (weekends, holidays, invalid tickers)

## Core Classes Structure

```python
# portfolio_manager.py

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import mysql.connector as sql_con
from contextlib import contextmanager

class PortfolioManager:
    """Main portfolio management class"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
    
    def create_portfolio(self, user_id: int, name: str, tickers: List[str], 
                        data_type: str, **kwargs) -> int:
        """Create new portfolio with constraints"""
        pass
    
    def add_stocks(self, portfolio_id: int, tickers: List[str]) -> bool:
        """Add stock(s) to existing interday portfolio (intraday is readonly)"""
        # Check if portfolio is interday and not readonly
        # Validate tickers using check_args()
        # Add to portfolio_stocks table
        # Fetch historical data for new stocks with existing date range
        pass
    
    def remove_stocks(self, portfolio_id: int, tickers: List[str]) -> bool:
        """Remove stock(s) from portfolio"""
        # Validate tickers using check_args()
        # Remove from portfolio_stocks table
        # Optionally clean up cached data
        pass
    
    def update_interval(self, portfolio_id: int, start_date: str, end_date: str) -> bool:
        """Update date range for interday portfolio and refetch data with new delta"""
        # Check if portfolio is interday
        # Validate dates using check_args()
        # Update portfolio metadata
        # Refetch all portfolio data with new date range
        # Handle smart fetching if extending vs contracting date range
        pass
    
    def fetch_portfolio_data(self, portfolio_id: int) -> pd.DataFrame:
        """Fetch current data for all stocks in portfolio"""
        pass
    
    def check_args(self, portfolio_id: int) -> None:
        """Display portfolio info so user can see what they have and decide what to do"""
        # Fetch portfolio metadata from database
        # Display: name, data_type, interval, date_range/period, readonly status
        # Show stock list with count
        # Display creation date and last edited date
        # Show data constraints and available operations
        # Format nicely for user decision-making
        pass
    
    def _validate_args(self, **kwargs) -> bool:
        """Internal validation function for backend operations"""
        # Validate tickers format
        # Validate date formats and ranges
        # Validate portfolio exists and user has access
        # Validate constraints (intraday vs interday rules)
        # Check business logic constraints
        pass
    
    @staticmethod
    def help(section: str = "main") -> None:
        """Display context-sensitive help and wait for user input"""
        help_text = {
            "main": """
                Portfolio Manager Help:
                - Create Portfolio: Set up new stock portfolio with automatic data fetching
                - Manage Portfolio: Add/remove stocks or update date ranges (interday only)
                - Intraday vs Interday: Determined by interval choice
                * Intraday (1m-1h): Limited to 60 days, readonly after creation
                * Interday (1d+): Flexible date ranges, can modify stocks and dates
                            """,
                            "portfolio": """
                Portfolio Management:
                - Add Stocks: Add new tickers to existing interday portfolio
                - Remove Stocks: Remove tickers from portfolio
                - Update Dates: Change start/end date range (refetches all data)
                - View Data: Display portfolio performance and holdings
            """
        }
        print(help_text.get(section, help_text["main"]))
        input("\nPress any key to return...")
        pass

class DataFetcher:
    """Handle yfinance data fetching with proper parameters"""
    
    @staticmethod
    def fetch_data(tickers: List[str], data_type: str, **kwargs) -> pd.DataFrame:
        """
        Fetch data using yf.download() with appropriate parameters
        
        Args:
            tickers: List of tickers
            data_type: 'intraday' or 'interday'
            **kwargs: yfinance parameters
        
        Returns:
            DataFrame with stock data
        """
        if data_type == 'intraday':
            # Validate 60-day limit for intraday
            period = kwargs.get('period', '5d')
            interval = kwargs.get('interval', '1h')
            
            # Ensure intraday constraints
            if interval in ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h']:
                return yf.download(
                    tickers,
                    period=period,
                    interval=interval,
                    ignore_tz=False,  # Keep timezone for intraday
                    group_by='ticker' if len(tickers) > 1 else 'column',
                    auto_adjust=True,
                    prepost=False,
                    threads=True,
                    keepna=False
                )
        else:  # interday
            start = kwargs.get('start')
            end = kwargs.get('end', datetime.now().date())
            interval = kwargs.get('interval', '1d')
            
            return yf.download(
                tickers,
                start=start,
                end=end,
                interval=interval,
                ignore_tz=True,   # Ignore timezone for daily+
                group_by='ticker' if len(tickers) > 1 else 'column',
                auto_adjust=True,
                prepost=False,
                threads=True,
                keepna=False
            )
```

## yfinance.download() Reference

```python
yfinance.download(tickers, start=None, end=None, actions=False, threads=True,
                 ignore_tz=None, group_by='column', auto_adjust=None, back_adjust=False,
                 repair=False, keepna=False, progress=True, period=None, interval='1d',
                 prepost=False, proxy=<object object>, rounding=False, timeout=10, session=None,
                 multi_level_index=True) → DataFrame | None
```

**Key Parameters for Portfolio Manager:**

- `tickers`: str, list - List of tickers to download
- `period`: str - Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max. Default: 1mo. Either use period parameter or use start and end
- `interval`: str - Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo. Intraday data cannot extend last 60 days
- `start`: str - Download start date string (YYYY-MM-DD) or datetime, inclusive. Default is 99 years ago
- `end`: str - Download end date string (YYYY-MM-DD) or datetime, exclusive. Default is now. Result *excludes* end date data.
- `group_by`: str - Group by 'ticker' or 'column' (default)
- `auto_adjust`: bool - Adjust all OHLC automatically? Default is True
- `ignore_tz`: bool - When combining from different timezones, ignore that part of datetime. Intraday = False, Day+ = True
- `keepna`: bool - Keep NaN rows returned by Yahoo? Default is False
- `threads`: bool/int - How many threads to use for mass downloading. Default is True

**Critical Constraints:**
- Intraday intervals (1m-1h): Cannot extend beyond 60 days
- Period vs start/end: Use either period OR start/end, not both - refer to flow design for more details
- Timezone handling: ignore_tz=False for intraday, ignore_tz=True for daily+

**Usage Examples:**
```python
# Intraday data (limited to 60 days)
data = yf.download(['AAPL', 'GOOGL'], period='30d', interval='1h', 
                   ignore_tz=False, group_by='ticker')

# Daily data with date range
data = yf.download(['AAPL', 'GOOGL'], start='2024-01-01', end='2024-12-31', 
                   interval='1d', ignore_tz=True, group_by='ticker')

# Single ticker (group_by='column' for cleaner DataFrame)
data = yf.download('AAPL', period='1y', interval='1d', group_by='column')
```

## Key Design Decisions

1. **On-demand fetching**: No persistent stock data storage initially
2. **Per-portfolio constraints**: Each portfolio has its own date/interval rules
3. **Read-only intraday**: Once created, intraday portfolios can't change date ranges
4. **Future enhancement**: extend_portfolio_dates() for smart date range updates

## Files to Create/Modify

```
portfolio_manager/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── portfolio.py          # PortfolioManager class
│   ├── data_fetcher.py       # DataFetcher class  
│   └── data_processor.py     # DataProcessor class
├── database/
│   ├── __init__.py
│   ├── connection.py         # Database connection management
│   └── migrations.sql        # Schema migration
├── cli/
│   ├── __init__.py
│   └── interface.py          # Updated CLI interface
├── utils/
│   ├── __init__.py
│   ├── validation.py         # Input validation
│   └── exceptions.py         # Custom exceptions
├── tests/
│   ├── test_portfolio.py
│   ├── test_data_fetcher.py
│   └── test_data_processor.py
├── requirements.txt
├── .env.example
└── README.md
```

## Environment Variables Needed

```bash
# .env
DB_HOST=localhost
DB_USER=your_username  
DB_PASSWORD=your_password
DB_NAME=Lab3

# Optional: API rate limiting
YFINANCE_DELAY=0.1
MAX_RETRIES=3
```

This is considerations to continue with the database migration + `PortfolioManager` class implementation later, if necessary. The existing `portfolio_manager_secure.py` can serve as reference for the CLI patterns we want to keep.