
ALTER TABLE pending_registrations ADD COLUMN verification_token TEXT;
CREATE INDEX idx_verification_token ON pending_registrations(verification_token);