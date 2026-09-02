# README.md

# Auth App

This project is a Flask-based application that provides user authentication and OTP (One-Time Password) verification functionality. Users can log in and receive an OTP via email for verification.

## Project Structure

```
auth-app
├── src
│   ├── app.py               # Main entry point of the application
│   ├── models
│   │   └── user.py          # User model definition
│   ├── templates
│   │   └── auth
│   │       ├── login.html   # Login page template
│   │       └── verify_otp.html # OTP verification page template
│   ├── utils
│   │   ├── email.py         # Email sending utilities
│   │   └── otp.py           # OTP generation and validation utilities
│   └── config.py            # Configuration settings
├── requirements.txt          # Project dependencies
└── README.md                 # Project documentation
```

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   ```

2. Navigate to the project directory:
   ```
   cd auth-app
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure the application settings in `src/config.py`, including email server details.

5. Run the application:
   ```
   python src/app.py
   ```

## Usage

- Navigate to `http://localhost:5000/login` to access the login page.
- Enter your credentials to log in and receive an OTP.
- Enter the OTP sent to your email on the OTP verification page.

## License

This project is licensed under the MIT License.