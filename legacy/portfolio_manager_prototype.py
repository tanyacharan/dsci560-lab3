import mysql.connector
import yfinance as yf

# Connect to MySQL (phpMyAdmin uses same credentials)
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",        # change if needed
        password="yourpassword",  # change if needed
        database="Lab3"
    )

def create_user_portfolio_table(username):
    conn = get_connection()
    cursor = conn.cursor()
    table_name = f"{username}_portfolio"
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open FLOAT,
        close FLOAT,
        volume BIGINT,
        UNIQUE(ticker, date)
    );
    """)
    conn.commit()
    cursor.close()
    conn.close()
    return table_name

def populate_portfolio(username, tickers):
    table_name = create_user_portfolio_table(username)
    conn = get_connection()
    cursor = conn.cursor()

    for ticker in tickers:
        ticker = ticker.strip().upper()
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")  # get last 5 days
        if hist.empty:
            print(f"❌ No data found for {ticker}")
            continue

        for date, row in hist.iterrows():
            cursor.execute(f"""
                INSERT IGNORE INTO {table_name} (ticker, date, open, close, volume)
                VALUES (%s, %s, %s, %s, %s)
            """, (ticker, date.date(), row['Open'], row['Close'], row['Volume']))
        print(f"✅ Inserted data for {ticker}")

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    username = input("Enter username (e.g. user1): ").strip()
    tickers = input("Enter stock tickers (comma separated): ").split(",")
    populate_portfolio(username, tickers)
