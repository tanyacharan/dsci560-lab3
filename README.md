# Portfolio Manager

A secure command-line portfolio management system that allows users to track stock portfolios with real-time data from Yahoo Finance. The system supports both intraday (high-frequency) and interday (daily+) data collection with user authentication and comprehensive portfolio management features.

## Features

### Portfolio Types
- **Intraday Portfolios**: High-frequency data (1m-1h intervals), limited to 60 days, read-only after creation
- **Interday Portfolios**: Daily+ data (1d-3mo intervals), flexible date ranges, fully modifiable

### Core Functionality
- User registration and secure authentication (password hashing with salt)
- Multiple portfolio creation and management
- Real-time stock data fetching from Yahoo Finance
- Add/remove stocks from portfolios
- Update date ranges for interday portfolios
- Simple portfolio performance metrics (todo more detailed metrics)
- Comprehensive help system

### Security Features
- SQL injection prevention with parameterized queries
- Password hashing with unique salts
- Environment variable configuration for credentials
- User session management
- Input validation and error handling

## Installation

### Prerequisites
- Python 3.7+
- MySQL Server
- Internet connection (for Yahoo Finance data)

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/tanyacharan/dsci560-lab3.git
   cd dsci560-lab3
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup MySQL Database**
   - Start your MySQL server
   - Create a database for the application:
   ```sql
   CREATE DATABASE Lab3;
   ```

4. **Configure Environment Variables**
   - Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   - Edit `.env` with your MySQL credentials:
   ```
   DB_HOST=localhost
   DB_USER=your_mysql_username
   DB_PASSWORD=your_mysql_password
   DB_NAME=Lab3
   ```

5. **Run the Application**
   ```bash
   python portfolio_manager_refactored.py
   ```

## Usage

### First Time Setup
1. Run the application
2. Choose "Register" to create a new account
3. Follow the password requirements (8+ chars, mixed case, numbers)
4. Login with your new credentials

### Managing Portfolios

#### Creating a Portfolio
1. Select "Create new portfolio"
2. Enter a descriptive name
3. Add stock tickers (comma-separated): `AAPL, MSFT, GOOGL`
4. Choose interval type:
   - **Intraday**: `1m, 2m, 5m, 15m, 30m, 1h`
   - **Interday**: `1d, 5d, 1wk, 1mo, 3mo`
5. Set time range:
   - **Intraday**: Period only (anywhere from `1d` to `60d`)
   - **Interday**: Start and end dates (`YYYY-MM-DD`)

#### Managing Existing Portfolios
1. Select "Select and manage portfolio"
2. Choose a portfolio from the list
3. View current holdings and portfolio information
4. Available actions:
   - View detailed stock data with performance metrics
   - Add new stocks (interday only)
   - Remove existing stocks
   - Update date range (interday only)
   - View comprehensive portfolio information

### Portfolio Workflow Example
```
Your Portfolios:
[1] tech_stocks
[2] dividend_plays

Enter portfolio name to manage: tech_stocks

============================================================
         PORTFOLIO: TECH_STOCKS
============================================================
Type: INTERDAY | Interval: 1d
Date Range: 2024-01-01 to 2024-12-31
Read-only: No

Current Holdings (3 stocks):
  AAPL, MSFT, GOOGL
============================================================

--- Managing: tech_stocks ---
1. View detailed stock data
2. Add stocks
3. Remove stocks
4. Update date range (interday only)
5. Portfolio information
0. Back to portfolio selection
```

## Data Types and Constraints

### Intraday Portfolios
- **Purpose**: Day trading and short-term analysis
- **Intervals**: 1m, 2m, 5m, 15m, 30m, 1h
- **Limitation**: Maximum 60 days of historical data
- **Behavior**: Read-only after creation (cannot add/remove stocks or change dates)

### Interday Portfolios
- **Purpose**: Long-term investing and analysis
- **Intervals**: 1d, 5d, 1wk, 1mo, 3mo
- **Limitation**: None (any historical date range)
- **Behavior**: Fully modifiable (can add/remove stocks and update date ranges)

## Help System

The application includes comprehensive help available at any input prompt:
- Type `help` or `?` at any prompt for context-sensitive help
- Main menu help explains all features and portfolio types
- Creation flow help guides through portfolio setup
- Interval and period help explains data type constraints

## Database Schema

The application automatically creates the following tables:

### `users`
- User authentication and account information
- Password hashing with unique salts
- Registration and login timestamps

### `portfolios`
- Portfolio metadata (name, type, date ranges, intervals)
- User ownership and read-only flags
- Creation and modification timestamps

### `portfolio_stocks`
- Many-to-many relationship between portfolios and stocks
- Stock addition timestamps
- Automatic cleanup on portfolio deletion

## Error Handling

The application includes comprehensive error handling for:
- Database connection issues
- Invalid stock tickers
- Network connectivity problems
- Invalid date ranges and intervals
- User input validation
- Portfolio ownership verification

## Performance Notes

- Data is fetched on-demand from Yahoo Finance (no local caching)
- Large date ranges or many stocks may take longer to fetch
- Intraday data fetching is faster due to smaller datasets
- Database queries are optimized with proper indexing

## Security Considerations

- Passwords are stored using SHA256 and unique salts
- All database queries use parameterized statements
- Environment variables protect database credentials
- User sessions prevent unauthorized access to portfolios
- Input validation prevents malicious data entry and injections

## Troubleshooting

### Common Issues

**Database Connection Failed**
- Verify MySQL server is running
- Check `.env` file credentials
- Ensure `Lab3` database exists

**No Data for Ticker**
- Verify ticker symbol is correct
- Check internet connection
- Some tickers may not have data for requested date range

**Invalid Date Range**
- Ensure dates are in YYYY-MM-DD format
- Start date must be before end date
- End date cannot be in the future

**Intraday Limitations**
- Cannot request more than 60 days of intraday data
- Cannot modify intraday portfolios after creation
- Use interday portfolios for longer historical analysis

## Support

For issues or questions:
1. Check the built-in help system (`help` command)
2. Review this README for common solutions
3. Verify your environment setup matches the requirements
4. Check MySQL server status and credentials
5. Reach out to repository owners for more details

## License

This project is provided as-is for educational and personal use.