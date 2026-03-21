# Router for managing the authenticated user's profile.
# Exposes REST endpoints under the /users prefix.
# Allows updating username, display_name and uploading a profile avatar.
# All operations require JWT authentication.

import os    # filesystem operations: create directory, remove old avatar file
import uuid  # generate unique filenames for uploaded avatar images

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

# ORM model and DB session factory
from database.db import User, get_db

# Pydantic schemas for request validation and response serialisation
from models.schemas import UserResponse, UserUpdate

# FastAPI dependency that extracts and validates the current user from the JWT
from services.auth_service import get_current_user

# Router prefix /users — all routes resolve to /api/users/...
router = APIRouter(prefix="/users", tags=["Utilizatori"])

# Relative path of the directory where avatar images are stored on disk
AVATARS_DIR = "static/avatars"


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),  # authenticated user injected from JWT
):
    """
    Return the full profile of the currently authenticated user.

    Includes all public fields: id, email, username, display_name, avatar_url, created_at.
    The hashed password is never exposed.

    Args:
        current_user: ORM User object injected via the JWT dependency.

    Returns:
        UserResponse with the current user's data.
    """
    # Return the ORM object directly; FastAPI serialises it via UserResponse
    return current_user


@router.put("/me", response_model=UserResponse)
def update_me(
    date: UserUpdate,                                # fields to update (username and/or display_name)
    db: Session = Depends(get_db),                  # SQLAlchemy session injected by FastAPI
    current_user: User = Depends(get_current_user), # authenticated user injected from JWT
):
    """
    Update the current user's profile (username and/or display_name).

    Supports partial updates — fields omitted from the request body are left unchanged.
    Validates username uniqueness before saving to prevent duplicates.

    Args:
        date:         Fields to update (all optional, partial-update semantics).
        db:           SQLAlchemy session shared with the get_current_user dependency.
        current_user: ORM User object attached to the same db session.

    Returns:
        UserResponse with the updated user data.

    Raises:
        HTTPException 400: if the request body contains no fields to update.
        HTTPException 409: if the requested username is already taken by another user.
    """
    # Extract only the fields that were explicitly provided in the request body.
    # exclude_unset=True prevents overwriting existing values with None for omitted fields.
    fields = date.model_dump(exclude_unset=True)  # dict containing only the explicitly sent fields

    # Return 400 if the caller sent an empty body — nothing to update
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    # If a new username was provided, verify it is not already taken by a different user
    if "username" in fields:
        existing = (
            db.query(User)
            .filter(
                User.username == fields["username"],  # same username
                User.id != current_user.id,           # but a different account
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )

    # Apply each updated field to the ORM object via setattr
    for field, value in fields.items():
        setattr(current_user, field, value)

    # Explicitly re-attach the object to the session to guarantee dirty-state tracking.
    # This is a defensive measure in case the object was in a detached or expired state
    # (e.g. due to an intermediate flush triggered by the get_current_user dependency).
    db.add(current_user)

    # Flush the dirty object to the DB and commit the transaction
    db.commit()

    # Reload the object from DB so the returned data reflects the final persisted state
    db.refresh(current_user)

    # FastAPI serialises the ORM object via UserResponse
    return current_user


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),                   # image file sent as multipart/form-data
    db: Session = Depends(get_db),                  # SQLAlchemy session injected by FastAPI
    current_user: User = Depends(get_current_user), # authenticated user injected from JWT
):
    """
    Upload a profile picture (avatar) for the currently authenticated user.

    The file is saved to static/avatars/ under a unique name composed of the user id
    and a random UUID hex to avoid collisions and prevent name guessing.
    The previous avatar is automatically deleted from disk if one exists.
    The avatar_url column in the DB is updated with the new relative URL.

    Accepted MIME types: image/jpeg, image/png, image/gif, image/webp.

    Args:
        file:         Uploaded image file (multipart/form-data).
        db:           SQLAlchemy session injected by FastAPI.
        current_user: ORM User object attached to the same db session.

    Returns:
        UserResponse with the updated avatar_url field.

    Raises:
        HTTPException 400: if the file MIME type is not supported.
    """
    # Set of accepted MIME types for avatar uploads
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}

    # Reject the upload early if the content type is not in the allowed set
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use JPEG, PNG, GIF or WebP.",
        )

    # Create the avatars directory if it does not exist yet (exist_ok avoids FileExistsError)
    os.makedirs(AVATARS_DIR, exist_ok=True)

    # Extract the file extension from the original filename; fall back to 'jpg' if absent
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"

    # Build a unique filename: "{user_id}_{uuid_hex}.{ext}" (e.g. "42_a3f1b2c4.jpg")
    # The random UUID prevents accidental overwrites and makes filenames unpredictable
    filename = f"{current_user.id}_{uuid.uuid4().hex}.{ext}"

    # Full relative path on disk (e.g. "static/avatars/42_abc123.jpg")
    filepath = os.path.join(AVATARS_DIR, filename)

    # Read the uploaded bytes and write them to disk
    content = await file.read()       # read the full file into memory from the request
    with open(filepath, "wb") as f:
        f.write(content)              # write bytes to the destination file

    # Delete the previous avatar from disk to avoid accumulating unused files
    if current_user.avatar_url:
        old_path = current_user.avatar_url.lstrip("/")  # strip leading slash for a valid OS path
        if os.path.exists(old_path):
            try:
                os.remove(old_path)   # remove the old image file
            except OSError:
                pass  # ignore errors if the file is already gone or cannot be removed

    # Update the avatar_url column with the HTTP-accessible relative path
    # The "/static/..." prefix is served by FastAPI's StaticFiles mount in main.py
    current_user.avatar_url = f"/static/avatars/{filename}"

    # Re-attach, commit and refresh — same defensive pattern as update_me
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return current_user
