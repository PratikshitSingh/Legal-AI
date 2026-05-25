# JWT Authentication Implementation - Quick Reference

## ✅ What Was Implemented

### 1. **Database Schema** (`db.py`)
- **users**: Email-based user registration (UUID primary key, email unique)
- **refresh_tokens**: Long-lived tokens (7 days) stored securely as hashes
- **magic_links**: Temporary tokens for passwordless sign-in (15 min expiry)
- **sessions**: Chat sessions linked to users via `user_id` FK
- **audit_log**: Conversation history (unchanged)

### 2. **JWT Token System** (`jwt_utils.py`)
- **Access tokens**: 15-minute JWT tokens (HS256 algorithm)
- **Refresh tokens**: 7-day random tokens (stored hashed in DB)
- Token generation: `create_access_token(user_id)` 
- Token validation: `validate_access_token(token)` → returns user_id
- Auto-refresh: Check expiry and refresh using refresh token

### 3. **Email Service** (`email_service.py`)
- **Magic links**: Email with sign-in link: `https://app.com/auth/verify?token=XXX`
- **Providers**: SendGrid (production), Local (development/testing)
- HTML formatted emails with 15-minute expiry message
- Configurable via `EMAIL_PROVIDER` env variable

### 4. **Authentication Flow** (`auth.py`)
**Before (Username-based):**
```
user enters username → stored in session state
```

**Now (Magic link passwordless):**
```
1. request_magic_link(email)
   → Creates token, hashes it, stores in DB
   → Sends email with magic link
   → Returns {"status": "success", "message": "Check your email"}

2. verify_magic_link_token(email, token)
   → Validates token against DB
   → Creates user if new
   → Generates access + refresh tokens
   → Returns tokens + user_id

3. Token stored in session state:
   - legal_ai_user_id (UUID)
   - legal_ai_user_email (email)
   - legal_ai_access_token (JWT)
   - legal_ai_refresh_token (random string)
```

### 5. **Streamlit UI** (`app.py`)
- **Sign-in page**: Email form (no username)
- **Magic link callback**: `/auth/verify?token=XXX` URL handler
- **Token refresh**: Auto-refresh on page load if expired
- **API calls**: Pass JWT token to `route_query(jwt=access_token)`

### 6. **Gateway JWT Validation** (`gateway.py`)
- `validate_jwt(token)` → returns (user_id, is_valid)
- Validates JWT signature and expiry
- Verifies user owns the session (prevents cross-session access)
- Returns user_id for tracing/audit

### 7. **Configuration** (`config.yaml`, `.env`)
```yaml
jwt:
  access_token_expires_seconds: 900        # 15 minutes
  refresh_token_expires_days: 7            # 7 days
  secret_env: JWT_SECRET                   # Load from env

email:
  provider: sendgrid                       # or 'local'
  from_address_env: EMAIL_FROM
  magic_link_expires_minutes: 15
```

**Environment variables to set:**
```bash
JWT_SECRET="your-secret-key-min-32-chars-recommended"
SENDGRID_API_KEY="your-sendgrid-api-key"  # Or skip for local dev
EMAIL_FROM="noreply@legal-ai.app"         # Optional
EMAIL_PROVIDER="local"                     # For dev; "sendgrid" for prod
```

---

## 🚀 Quick Start

### 1. **Install dependencies**
```bash
pip install PyJWT email-validator sendgrid
```

### 2. **Set environment variables** (for local development)
```bash
export JWT_SECRET="my-super-secret-key-at-least-32-chars"
export EMAIL_PROVIDER="local"  # Will print emails to console
```

### 3. **Run the app**
```bash
streamlit run app.py
```

### 4. **Test magic link flow**
1. Enter your email at sign-in
2. Check console output (since EMAIL_PROVIDER=local)
3. Copy the magic link from console
4. Click the link or manually navigate to `http://localhost:8501/auth/verify?token=<token>`
5. Confirm email address on the page
6. Authenticated! ✅

---

## 📊 Authentication Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     SIGN-IN FLOW (Magic Link)              │
└─────────────────────────────────────────────────────────────┘

User enters email
    ↓
request_magic_link(email)
    ├─ Generate random token
    ├─ Hash and store in DB (magic_links table)
    ├─ Send HTML email with link
    └─ Show "Check your email"
    ↓
User clicks email link
    ├─ URL: /auth/verify?token=<token>
    ├─ Streamlit callback handles it
    └─ Show email confirmation form
    ↓
User confirms email, submits token
    ↓
verify_magic_link_token(email, token)
    ├─ Validate token against DB
    ├─ Mark token as used
    ├─ Create user (if new)
    ├─ Generate access token (JWT, 15min)
    ├─ Generate refresh token (random, 7 days)
    ├─ Store refresh token hash in DB
    └─ Return tokens to client
    ↓
Tokens stored in Streamlit session state
    ├─ legal_ai_access_token (sent with API requests)
    ├─ legal_ai_refresh_token (only for refresh)
    └─ legal_ai_user_id (for audit/tracing)
    ↓
Ready to chat! ✅


┌─────────────────────────────────────────────────────────────┐
│              API CALL WITH JWT AUTHENTICATION              │
└─────────────────────────────────────────────────────────────┘

route_query(question, session_id, jwt=access_token)
    ├─ validate_jwt(access_token)
    │  ├─ Decode JWT (verify signature)
    │  ├─ Check expiry
    │  ├─ Extract user_id
    │  └─ Return (user_id, is_valid)
    ├─ Verify user owns session
    │  ├─ Get session_user_id from DB
    │  └─ Ensure matches JWT user_id
    ├─ Log message to audit_log
    ├─ Run RAG pipeline
    ├─ Log response
    └─ Return answer


┌─────────────────────────────────────────────────────────────┐
│           TOKEN REFRESH (Auto on page load)               │
└─────────────────────────────────────────────────────────────┘

Page loads → refresh_access_token_if_needed()
    ├─ Get access_token from session state
    ├─ Check if expired: is_access_token_expired()
    │  ├─ Decode JWT without verification
    │  └─ Check exp claim
    ├─ If expired:
    │  ├─ Get refresh_token from session state
    │  ├─ Validate refresh_token in DB
    │  ├─ Generate new access_token
    │  ├─ Update session state
    │  └─ Continue with fresh token
    └─ Continue with chat
```

---

## 🔐 Security Details

### Password Hashing
- **Magic links**: `hashlib.sha256(token).hexdigest()`
- **Refresh tokens**: `hashlib.sha256(token).hexdigest()`
- **Stored only as hashes** in DB (can't extract original tokens)

### Token Expiry
- **Access tokens**: 15 minutes (short-lived, used for API requests)
- **Refresh tokens**: 7 days (long-lived, used only to get new access tokens)
- **Magic links**: 15 minutes (one-time use only)

### Session Isolation
- Each user_id can have multiple sessions
- JWT token includes user_id
- Gateway verifies user owns the session
- Prevents: User A accessing User B's chats

### Revocation
- `sign_out()` → `db.revoke_refresh_tokens(user_id)`
- Sets `revoked_at` timestamp on refresh tokens
- Old tokens no longer valid on next request
- Immediate sign-out effect

---

## 📝 API Examples

### Request Magic Link
```python
from auth import request_magic_link

result = request_magic_link("user@example.com")
# {"status": "success", "message": "Check your email..."}
# or
# {"status": "error", "message": "..."}
```

### Verify Magic Link Token
```python
from auth import verify_magic_link_token, set_auth_tokens

result = verify_magic_link_token("user@example.com", "token_123...")
if result["status"] == "success":
    set_auth_tokens(
        user_id=result["user_id"],
        email=result["email"],
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
    )
    # User is now authenticated!
```

### Get Current User
```python
from auth import get_current_user_id, get_current_user

user_id = get_current_user_id()  # UUID
email = get_current_user()        # Email string
```

### Refresh Token
```python
from auth import refresh_access_token_if_needed

success = refresh_access_token_if_needed()  # Returns True if valid/refreshed
```

### Make API Call with JWT
```python
from auth import get_current_access_token
from gateway import route_query

token = get_current_access_token()
answer = route_query(
    question="What is the EU AI Act?",
    session_id="session-uuid",
    jwt=token
)
```

---

## 🧪 Testing

### Run End-to-End Tests
```bash
JWT_SECRET="test-key" python test_auth_flow.py
```

**Results (8/8 passing):**
- ✓ Database initialization
- ✓ User creation
- ✓ Magic link flow
- ✓ JWT token generation/validation
- ✓ Refresh token flow
- ✓ Token revocation
- ✓ Session management
- ✓ Email service

---

## 📚 File Reference

| File | Purpose |
|------|---------|
| `db.py` | Database schema + CRUD operations |
| `jwt_utils.py` | JWT token generation, validation, refresh |
| `email_service.py` | Magic link email sending (SendGrid/Local) |
| `auth.py` | Magic link sign-in, token management, session handling |
| `gateway.py` | JWT validation, session ownership verification |
| `app.py` | Streamlit UI with magic link callback |
| `config.yaml` | JWT and email configuration |
| `.env.example` | Environment variables template |
| `test_auth_flow.py` | End-to-end authentication tests |

---

## ⚙️ Production Deployment Checklist

- [ ] Generate strong `JWT_SECRET` (32+ random characters)
- [ ] Configure SendGrid API key (`SENDGRID_API_KEY`)
- [ ] Set `EMAIL_FROM` to your domain
- [ ] Set `EMAIL_PROVIDER=sendgrid` in production
- [ ] Update `APP_BASE_URL` to your Streamlit domain (for magic links)
- [ ] Test end-to-end: `python test_auth_flow.py`
- [ ] Review database schema migration
- [ ] Enable HTTPS on production
- [ ] Monitor magic link email delivery rates
- [ ] Set up token expiry monitoring (access: 15min, refresh: 7 days)
- [ ] Document sign-out procedures for admins

---

## 🎯 What's Next?

### Optional Enhancements
1. **Multi-device support**: Store multiple refresh tokens (one per device)
2. **RBAC**: Add `role` column to users table (admin, viewer, lawyer)
3. **2FA**: Two-factor authentication for high-security users
4. **OAuth**: Add Google/Microsoft sign-in
5. **Profile**: First name, firm, profile picture
6. **API Dashboard**: Management endpoints for admins
7. **Rate limiting**: Limit magic link requests per email/IP
8. **Email verification**: Resend verification if bounced

---

**Questions?** Check the test file (`test_auth_flow.py`) for working examples of each feature.
