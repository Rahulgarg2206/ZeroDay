class User:
    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = password  # In a real application, this should be hashed

    def save_to_db(self):
        # Logic to save the user to the database
        pass

    @classmethod
    def find_by_username(cls, username):
        # Logic to find a user by username in the database
        pass

    @classmethod
    def verify_credentials(cls, username, password):
        # Logic to verify user credentials
        pass

    @classmethod
    def get_user_by_email(cls, email):
        # Logic to get a user by email
        pass