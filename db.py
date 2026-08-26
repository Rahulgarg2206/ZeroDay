import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

def create_database_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get("DB_HOST"),  # Your cPanel MySQL host
            user=os.environ.get("DB_USER"),  # Your cPanel MySQL username
            password=os.environ.get("DB_PASSWORD"),  # Your cPanel MySQL password
            database=os.environ.get("DB_NAME")  # Your database name
        )
        if connection.is_connected():
            print("Successfully connected to the database")
            return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def create_table(connection):
    try:
        cursor = connection.cursor()
        
        # SQL query to create a table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        cursor.execute(create_table_query)
        connection.commit()
        print("Table created successfully")
        
    except Error as e:
        print(f"Error creating table: {e}")
    finally:
        if connection.is_connected():
            cursor.close()

def main():
    # Create connection
    connection = create_database_connection()
    
    if connection is not None:
        # Create table
        create_table(connection)
        
        # Close the connection
        if connection.is_connected():
            connection.close()
            print("MySQL connection closed")

if __name__ == "__main__":
    main()
