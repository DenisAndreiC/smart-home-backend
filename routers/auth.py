# Router for user authentication and account management.
# Exposes REST endpoints under the /auth prefix.
# Handles registration, login, profile retrieval, preferences, password change,
# password reset, and email verification.

import logging
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ORM models and DB session factory
from database.db import User, UserPreferences, get_db

# Pydantic schemas for request validation and response serialisation
from models.schemas import (
    ChangePasswordRequest,    # Body for POST /auth/change-password
    ForgotPasswordRequest,    # Body for POST /auth/forgot-password
    ResetPasswordRequest,     # Body for POST /auth/reset-password
    Token,                    # Response schema for JWT token
    UserLogin,                # Body for POST /auth/login
    UserPreferencesResponse,  # Response schema for user preferences
    UserPreferencesUpdate,    # Body for PUT /auth/preferences
    UserRegister,             # Body for POST /auth/register
    UserResponse,             # Response schema for user data
)

# Auth service helpers
from services.auth_service import (
    create_access_token,  # Creates a signed JWT token
    get_current_user,     # FastAPI dependency: extracts user from Bearer token
    hash_password,        # Hashes a plain-text password with bcrypt
    verify_password,      # Compares plain-text password against a bcrypt hash
)

# Email service — sends real emails via Gmail SMTP
from services.email_service import send_email

# Custom exceptions for duplicate account data
from utils.exceptions import DuplicateEmailException, DuplicateUsernameException

router = APIRouter(prefix="/auth", tags=["Autentificare"])

# Base URL used in email links — points to the backend API
_BASE_URL = "http://192.168.100.184:8000/api/auth"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(date: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user and send a real verification email.

    Checks uniqueness of email and username before creation.
    Password is hashed with bcrypt — never stored in plain text.
    A verification email is sent via Gmail SMTP after account creation.

    Args:
        date: Registration data (email, username, password) validated by Pydantic
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        UserResponse with the newly created user data (HTTP 201 Created)

    Raises:
        DuplicateEmailException    - if the email already exists (HTTP 409)
        DuplicateUsernameException - if the username already exists (HTTP 409)
    """
    # Check if a user with the same email already exists
    if db.query(User).filter(User.email == date.email).first():
        raise DuplicateEmailException()  # HTTP 409 Conflict

    # Check if a user with the same username already exists
    if db.query(User).filter(User.username == date.username).first():
        raise DuplicateUsernameException()  # HTTP 409 Conflict

    # Generate a one-time email verification token (UUID4 hex)
    verification_token = uuid.uuid4().hex

    # Create the ORM object for the new user.
    # Password is hashed with bcrypt — the plain-text password is never stored.
    # is_verified starts as False; set to True after the user clicks the verification link.
    user_nou = User(
        email=date.email,
        username=date.username,
        hashed_password=hash_password(date.password),
        is_verified=False,
        verification_token=verification_token,
    )

    db.add(user_nou)
    db.commit()
    db.refresh(user_nou)

    # Send real verification email via Gmail SMTP
    verify_link = f"{_BASE_URL}/verify-email?token={verification_token}"
    await send_email(
        date.email,
        "SmartHome - Verify your email",
        (
            "Welcome to SmartHome!\n\n"
            "Click the link below to verify your email:\n"
            f"{verify_link}\n\n"
            "If you did not create this account, ignore this email."
        ),
    )

    return user_nou


@router.post("/login", response_model=Token)
def login(date: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate the user and return a JWT Bearer token.

    Uses a generic error message to avoid leaking whether an email exists.

    Args:
        date: Login credentials (email + password) validated by Pydantic
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        Token with access_token (signed JWT) and token_type = "bearer"

    Raises:
        HTTPException 401 Unauthorized - if email does not exist or password is wrong
    """
    user = db.query(User).filter(User.email == date.email).first()

    if not user or not verify_password(date.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email sau parola incorecta",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user.email})
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """
    Return the currently authenticated user's data.

    Protected endpoint — requires a valid JWT Bearer token.
    """
    return current_user


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's preferences.

    Creates default preferences if none exist yet.
    The ORM field 'tz' is exposed as 'timezone' in the API response.
    """
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)

    return UserPreferencesResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        timezone=prefs.tz,
        language=prefs.language,
        theme=prefs.theme,
        notifications_enabled=prefs.notifications_enabled,
        auto_detect_routines=prefs.auto_detect_routines,
    )


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_preferences(
    date: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the authenticated user's preferences (partial update — only sent fields change).

    Maps the 'timezone' API field to the ORM 'tz' column.
    Creates default preferences if none exist before applying the update.
    """
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    campuri = date.model_dump(exclude_unset=True)

    for camp, val in campuri.items():
        attr = "tz" if camp == "timezone" else camp
        setattr(prefs, attr, val)

    db.commit()
    db.refresh(prefs)

    return UserPreferencesResponse(
        id=prefs.id,
        user_id=prefs.user_id,
        timezone=prefs.tz,
        language=prefs.language,
        theme=prefs.theme,
        notifications_enabled=prefs.notifications_enabled,
        auto_detect_routines=prefs.auto_detect_routines,
    )


@router.post("/request-password-change")
async def request_password_change(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a 6-digit OTP to the authenticated user's email for password change verification.

    Generates a random 6-digit code, stores it with a 10-minute expiry, and emails it.
    The code is consumed by POST /auth/change-password via the email_code field.

    Args:
        db:           SQLAlchemy session injected by FastAPI
        current_user: Authenticated user from JWT

    Returns:
        {"message": "Verification code sent to your email"}
    """
    # Generate a random 6-digit numeric code
    code = str(random.randint(100000, 999999))

    # Store the code and its expiry (10 minutes from now, UTC)
    current_user.password_change_code = code
    current_user.password_change_code_expires = datetime.utcnow() + timedelta(minutes=10)
    db.add(current_user)
    db.commit()

    await send_email(
        current_user.email,
        "SmartHome - Password Change Code",
        (
            f"Your verification code is: {code}\n\n"
            "This code expires in 10 minutes.\n\n"
            "If you did not request this, ignore this email."
        ),
    )

    return {"message": "Verification code sent to your email"}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change the authenticated user's password.

    Supports two verification methods:
      - Variant A: provide current_password (verified against bcrypt hash)
      - Variant B: provide email_code (6-digit OTP sent via /request-password-change)

    At least one of current_password or email_code must be present.
    After a successful change, a confirmation email is sent to the user.

    Args:
        body:         {current_password?, email_code?, new_password}
        db:           SQLAlchemy session injected by FastAPI
        current_user: Authenticated user from JWT

    Returns:
        {"message": "Password changed successfully"}

    Raises:
        HTTPException 400: if neither verification method is provided,
                           if the current password is wrong,
                           if the OTP is invalid or expired,
                           or if new_password is shorter than 6 characters
    """
    # Require at least one verification method
    if not body.current_password and not body.email_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either current password or email verification code",
        )

    if len(body.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )

    if body.email_code:
        # Verify the OTP: must match and not be expired
        code_valid = (
            current_user.password_change_code is not None
            and current_user.password_change_code == body.email_code
            and current_user.password_change_code_expires is not None
            and current_user.password_change_code_expires > datetime.utcnow()
        )
        if not code_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification code",
            )
        # Invalidate the code after a single successful use
        current_user.password_change_code = None
        current_user.password_change_code_expires = None

    else:
        # Verify the current password against the stored bcrypt hash
        if not verify_password(body.current_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    # Hash and save the new password
    current_user.hashed_password = hash_password(body.new_password)
    db.add(current_user)
    db.commit()

    # Send confirmation email so the user is alerted about the change
    await send_email(
        current_user.email,
        "SmartHome - Password Changed",
        (
            "Your password was changed successfully. "
            "If you did not do this, contact support immediately."
        ),
    )

    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiate a password reset flow — sends a real reset link via email.

    Generates a UUID4 reset token, saves it, then emails the reset link.
    Always returns a generic message regardless of whether the email exists,
    to avoid leaking account information.

    Args:
        body: {email}
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        {"message": "If that email exists, a reset link has been sent."}
    """
    user = db.query(User).filter(User.email == body.email).first()

    if user:
        # Generate a one-time reset token and store it on the user record
        token = uuid.uuid4().hex
        user.reset_token = token
        db.add(user)
        db.commit()

        # Send real password reset email via Gmail SMTP
        reset_link = f"{_BASE_URL}/reset-password-page?token={token}"
        await send_email(
            body.email,
            "SmartHome - Reset your password",
            (
                "You requested a password reset.\n\n"
                "Click the link below:\n"
                f"{reset_link}\n\n"
                "If you did not request this, ignore this email."
            ),
        )

    # Always return the same response — do not reveal whether the email exists
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Complete a password reset using the token from the forgot-password flow.

    Looks up the user by reset_token, sets the new password, and clears the token.

    Args:
        body: {token, new_password}
        db:   SQLAlchemy session injected by FastAPI

    Returns:
        {"message": "Password has been reset successfully."}

    Raises:
        HTTPException 400: if the token is invalid or has already been used
    """
    user = db.query(User).filter(User.reset_token == body.token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    # Update the password and invalidate the token so it cannot be reused
    user.hashed_password = hash_password(body.new_password)
    user.reset_token = None
    db.add(user)
    db.commit()

    return {"message": "Password has been reset successfully."}


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Verify a user's email address using the token sent at registration.

    Marks the user as verified and clears the verification token.
    Returns an HTML page (not JSON) — the user opens this link from their email client.

    Args:
        token: UUID hex token from the registration verification link
        db:    SQLAlchemy session injected by FastAPI

    Returns:
        HTMLResponse: success page the user sees in their browser

    Raises:
        HTTPException 400: if the token is invalid or has already been used
    """
    user = db.query(User).filter(User.verification_token == token).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    # Mark the account as verified and clear the single-use token
    user.is_verified = True
    user.verification_token = None
    db.add(user)
    db.commit()

    return HTMLResponse(
        content=(
            "<html><body style='text-align:center;padding:50px;font-family:sans-serif'>"
            "<h1>Email Verified!</h1>"
            "<p>Your SmartHome account is now active. You can close this page.</p>"
            "</body></html>"
        )
    )


@router.get("/reset-password-page", response_class=HTMLResponse)
def reset_password_page(token: str):
    """
    Serve an HTML form that allows the user to set a new password.

    The form submits to POST /api/auth/reset-password via JavaScript fetch.
    Styled to match the app's dark theme (#0D1B2A background, #00BCD4 accent).

    Args:
        token: UUID hex reset token from the forgot-password email link

    Returns:
        HTMLResponse: the password reset form page
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>SmartHome - Reset Password</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0D1B2A;
      color: #e0e0e0;
      font-family: sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }}
    .card {{
      background: #162032;
      border-radius: 12px;
      padding: 40px 32px;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    }}
    h1 {{
      color: #00BCD4;
      font-size: 1.6rem;
      margin-bottom: 8px;
    }}
    p.subtitle {{
      color: #90a4ae;
      margin-bottom: 28px;
      font-size: 0.95rem;
    }}
    label {{
      display: block;
      margin-bottom: 6px;
      font-size: 0.9rem;
      color: #b0bec5;
    }}
    input[type=password] {{
      width: 100%;
      padding: 10px 14px;
      border: 1px solid #263547;
      border-radius: 8px;
      background: #1e2e40;
      color: #e0e0e0;
      font-size: 1rem;
      margin-bottom: 18px;
      outline: none;
      transition: border-color 0.2s;
    }}
    input[type=password]:focus {{
      border-color: #00BCD4;
    }}
    button {{
      width: 100%;
      padding: 12px;
      background: #00BCD4;
      color: #0D1B2A;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s;
    }}
    button:hover {{ background: #00acc1; }}
    #msg {{
      margin-top: 18px;
      text-align: center;
      font-size: 0.95rem;
      min-height: 20px;
    }}
    .error {{ color: #ef5350; }}
    .success {{ color: #00BCD4; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Reset Password</h1>
    <p class="subtitle">Enter your new password below.</p>
    <form id="resetForm">
      <input type="hidden" id="token" value="{token}">
      <label for="pw">New Password</label>
      <input type="password" id="pw" placeholder="New password" required minlength="6">
      <label for="pw2">Confirm Password</label>
      <input type="password" id="pw2" placeholder="Confirm password" required minlength="6">
      <button type="submit">Reset Password</button>
    </form>
    <div id="msg"></div>
  </div>
  <script>
    document.getElementById('resetForm').addEventListener('submit', async function(e) {{
      e.preventDefault();
      const token = document.getElementById('token').value;
      const pw = document.getElementById('pw').value;
      const pw2 = document.getElementById('pw2').value;
      const msg = document.getElementById('msg');

      if (pw !== pw2) {{
        msg.className = 'error';
        msg.textContent = 'Passwords do not match.';
        return;
      }}

      try {{
        const res = await fetch('/api/auth/reset-password', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ token: token, new_password: pw }})
        }});
        if (res.ok) {{
          document.getElementById('resetForm').style.display = 'none';
          msg.className = 'success';
          msg.textContent = 'Password reset successfully! You can close this page.';
        }} else {{
          const data = await res.json();
          msg.className = 'error';
          msg.textContent = data.detail || 'Something went wrong. Please try again.';
        }}
      }} catch (err) {{
        msg.className = 'error';
        msg.textContent = 'Network error. Please try again.';
      }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)
