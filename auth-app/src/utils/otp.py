import random
import time

class OTPManager:
    def __init__(self):
        self.otp_storage = {}

    def generate_otp(self, user_id):
        otp = random.randint(100000, 999999)
        self.otp_storage[user_id] = {
            'otp': otp,
            'timestamp': time.time()
        }
        return otp

    def validate_otp(self, user_id, otp):
        if user_id in self.otp_storage:
            stored_otp = self.otp_storage[user_id]['otp']
            timestamp = self.otp_storage[user_id]['timestamp']
            if time.time() - timestamp < 300:  # OTP is valid for 5 minutes
                if stored_otp == otp:
                    del self.otp_storage[user_id]  # Remove OTP after validation
                    return True
        return False