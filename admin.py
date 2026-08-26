import sqlite3
import hashlib
import os

DATABASE_FOLDER = 'database'
DATABASE_PATH = os.path.join(DATABASE_FOLDER, 'database.db')

def hash_password(password):
    """Hash the password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def add_admin(username, email, password):
    """Add a new admin to the database."""
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    
    try:
        # Insert new admin into the users table
        c.execute('''INSERT INTO users (username, email, password, is_leader) 
                     VALUES (?, ?, ?, ?)''', 
                  (username, email, hash_password(password), 1))
        conn.commit()
        print("Admin added successfully.")
    except sqlite3.IntegrityError:
        print("Error: Username or email already exists.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        conn.close()

def main():
    """Main function to run the CLI program."""
    print("Add a new admin")
    username = input("Enter username: ")
    email = input("Enter email: ")
    password = input("Enter password: ")
    
    add_admin(username, email, password)

if __name__ == "__main__":
    main() 